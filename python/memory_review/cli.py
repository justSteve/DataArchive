"""Command line for the memory review pipeline. [da-04r]

    python3 -m memory_review collect        # pull CM + local memory tiers
    python3 -m memory_review packet         # build the review packet
    python3 -m memory_review publish        # build + render the desk page
    python3 -m memory_review serve          # run the capture endpoint
    python3 -m memory_review status         # what ran, when, and is it healthy
    python3 -m memory_review import <file>  # record a downloaded decisions file
    python3 -m memory_review traffic        # what this pipeline asked CM, and got
    python3 -m memory_review config         # effective configuration

Exit codes are uniform across the run commands and cron reads them:
  0 healthy · 1 degraded · 2 failed.

`status` inverts that on purpose — it is a query, not a run, so it exits 0 when
it could answer and 2 when it could not.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import analyze, collect, config, heartbeat, ledger, render, server
from .store import Store


def _print_report(report: heartbeat.RunReport, verbose: bool) -> None:
    print(report.summary_line(), flush=True)
    for assertion in report.assertions:
        if assertion.failed() or verbose:
            marker = "FAIL" if assertion.failed() else "ok  "
            print(f"  [{marker}] {assertion.name}: {assertion.detail}", flush=True)


def cmd_collect(args: argparse.Namespace) -> int:
    config.ensure_dirs()
    report = collect.run(since=args.since)
    _print_report(report, args.verbose)
    return report.exit_code()


def cmd_packet(args: argparse.Namespace) -> int:
    config.ensure_dirs()
    packet_id, report = analyze.build(window_from=args.since)
    _print_report(report, args.verbose)
    if packet_id is not None:
        print(f"  packet {packet_id} built", flush=True)
    return report.exit_code()


def cmd_publish(args: argparse.Namespace) -> int:
    config.ensure_dirs()
    packet_id, report = analyze.build(window_from=args.since)
    _print_report(report, args.verbose)

    if packet_id is None:
        print("NO PACKET BUILT — nothing to publish. The desk page is left "
              "untouched rather than replaced with an empty one, so the page Steve "
              "has bookmarked still shows the last real packet.", flush=True)
        return max(report.exit_code(), 2)

    with Store() as store:
        payload = analyze.packet_payload(store, packet_id)
        path = render.write_page(payload, path=args.out)
        store.set_packet_page(packet_id, str(path))

    print(f"  desk page: {path}", flush=True)
    print(f"  file://wsl.localhost/Zgent{path}", flush=True)
    print(f"  http://{config.ENDPOINT_HOST}:{config.ENDPOINT_PORT}/review", flush=True)
    return report.exit_code()


def cmd_serve(args: argparse.Namespace) -> int:
    server.serve(host=args.host, port=args.port)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    checks = [
        ("collect", config.COLLECT_HEARTBEAT, config.COLLECT_STALE_AFTER_SECONDS),
        ("packet", config.PACKET_HEARTBEAT, config.PACKET_STALE_AFTER_SECONDS),
        ("endpoint", config.ENDPOINT_HEARTBEAT, config.ENDPOINT_STALE_AFTER_SECONDS),
    ]
    document: dict = {"jobs": {}}
    worst_state = "ok"
    rank = {"ok": 0, "degraded": 1, "stale": 2, "failed": 3, "unreadable": 3,
            "missing": 3}

    for name, path, stale_after in checks:
        verdict = heartbeat.evaluate(path, stale_after)
        document["jobs"][name] = {
            "state": verdict["state"], "ts": verdict["ts"],
            "age_seconds": verdict["age_seconds"], "message": verdict["message"],
            "counters": (verdict["document"] or {}).get("counters"),
        }
        if rank.get(verdict["state"], 3) > rank.get(worst_state, 0):
            worst_state = verdict["state"]

    try:
        with Store() as store:
            packet = store.latest_packet()
            document["latest_packet"] = dict(packet) if packet else None
            document["utterances"] = store.utterance_count()
            document["traffic_all_time"] = store.traffic_summary()
        document["ledger"] = ledger.stats()
    except Exception as exc:  # noqa: BLE001
        document["store_error"] = f"{type(exc).__name__}: {exc}"
        worst_state = "failed"

    document["overall"] = worst_state

    if args.json:
        print(json.dumps(document, indent=2, default=str))
        return 0 if "store_error" not in document else 2

    print(f"MEMORY REVIEW: {worst_state.upper()}")
    for name, info in document["jobs"].items():
        age = f"{info['age_seconds']}s ago" if info["age_seconds"] is not None else "never"
        print(f"  {name:<9} {info['state']:<10} {age:<14} {info['message']}")
    packet = document.get("latest_packet")
    if packet:
        print(f"  packet     #{packet['id']} · {packet['status']} · "
              f"{packet['item_count']} items · built {packet['built_at']}")
    else:
        print("  packet     none built yet")
    print(f"  corpus     {document.get('utterances', 0)} utterances collected")
    traffic = document.get("traffic_all_time") or {}
    print(f"  cm traffic {traffic.get('requests', 0)} requests, "
          f"{traffic.get('failed', 0)} failed, "
          f"{traffic.get('bytes_in', 0)} bytes")
    led = document.get("ledger") or {}
    print(f"  ledger     {led.get('entries', 0)} adjudications across "
          f"{led.get('packets_reviewed', 0)} packet(s) {led.get('decisions', {})}")
    if "store_error" in document:
        print(f"  STORE ERROR: {document['store_error']}")
        return 2
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.is_file():
        print(f"no such file: {path}", file=sys.stderr)
        return 2
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"cannot read {path}: {exc}", file=sys.stderr)
        return 2
    document.setdefault("source", "downloaded-file")
    result = server.apply_submission(document)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 2


def cmd_traffic(args: argparse.Namespace) -> int:
    with Store() as store:
        rows = store.conn.execute(
            "SELECT ts, path, status, ok, duration_ms, bytes_in, rows, error"
            " FROM cm_traffic ORDER BY id DESC LIMIT ?", (args.limit,)).fetchall()
        summary = store.traffic_summary(args.since)
    if args.json:
        print(json.dumps({"summary": summary, "recent": [dict(r) for r in rows]},
                         indent=2, default=str))
        return 0
    print(f"CM traffic: {summary['requests']} requests, {summary['failed']} failed, "
          f"{summary['bytes_in']} bytes, {summary['total_ms']}ms total")
    for row in rows:
        flag = "ok " if row["ok"] else "ERR"
        print(f"  {row['ts']} {flag} {str(row['status'] or '-'):>4} "
              f"{row['duration_ms']:>6}ms {str(row['rows'] or '-'):>5} rows  "
              f"{row['path']}{'  ' + row['error'] if row['error'] else ''}")
    print(f"\n  raw per-request log: {config.MOO_LOG_DIR}/cm-traffic-<date>.jsonl")
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    print(config.describe())
    layout = config.discover_layout()
    print(json.dumps({
        "instruction_surfaces": [s.repo for s in layout.surfaces],
        "okf_bundles": [f"{b.repo}:{b.path}" for b in layout.bundles],
        "auto_memory_dirs": [str(p) for p in layout.memory_dirs],
    }, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="memory_review",
        description="CM-to-DataArchive memory review pipeline [da-04r]")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="print passing assertions too")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("collect", help="pull CM + local memory tiers")
    p.add_argument("--since", help="ISO timestamp override for the CM cursor")
    p.set_defaults(func=cmd_collect)

    p = sub.add_parser("packet", help="build the review packet")
    p.add_argument("--since", help="ISO timestamp override for the review window")
    p.set_defaults(func=cmd_packet)

    p = sub.add_parser("publish", help="build the packet and render the desk page")
    p.add_argument("--since", help="ISO timestamp override for the review window")
    p.add_argument("--out", help="override the desk page path")
    p.set_defaults(func=cmd_publish)

    p = sub.add_parser("serve", help="run the capture endpoint")
    p.add_argument("--host", default=None)
    p.add_argument("--port", type=int, default=None)
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("status", help="heartbeat and store health")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("import", help="record a decisions file downloaded from the page")
    p.add_argument("file")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("traffic", help="what this pipeline asked CM, and what it got")
    p.add_argument("--limit", type=int, default=25)
    p.add_argument("--since", help="ISO timestamp lower bound for the summary")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_traffic)

    p = sub.add_parser("config", help="effective configuration and discovered inputs")
    p.set_defaults(func=cmd_config)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    except config.ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 — a crash must be legible, not a traceback
        print(f"memory-review FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
