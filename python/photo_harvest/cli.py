"""Command line for the Photo Description Harvest. [co-06tcu]

    python -m photo_harvest inventory [--limit N] [--recheck]
    python -m photo_harvest prepare   [--limit N]   # prepare + local screen
    python -m photo_harvest status
    python -m photo_harvest held                   # held photos, by location only
    python -m photo_harvest check                  # one tiny request: key and credit
    python -m photo_harvest send --size 200        # one batch: submit, wait, store, delete
    python -m photo_harvest collect BATCH_ID       # finish a batch after an interruption
    python -m photo_harvest page                   # desk page of described photos
    python -m photo_harvest run --chunk 300        # prepare + send until nothing is left

Run from DataArchive/python with its .venv. Every stage resumes from the
status column; Ctrl+C is safe between photos.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from . import inventory, store
from .config import Config
from .prepare import PrepareError, prepare_one, work_path

log = logging.getLogger("photo_harvest")


def cmd_inventory(cfg: Config, args) -> int:
    with store.connect(cfg.db_path) as conn:
        tally = inventory.run(conn, cfg, limit=args.limit, recheck=args.recheck)
    print(json.dumps(tally, sort_keys=True))
    return 0


def cmd_prepare(cfg: Config, args, screener=None) -> int:
    if screener is None:
        from .screen import Screener
        screener = Screener(cfg.screen_threshold)
    done = {"ready": 0, "held_sensitive": 0, "unreadable": 0, "skipped_small": 0}
    with store.connect(cfg.db_path) as conn:
        for row in store.by_status(conn, "pending", args.limit):
            sha, dest = row["sha256"], work_path(cfg, row["sha256"])
            try:
                info = prepare_one(row["source_path"], dest, cfg)
            except PrepareError as exc:
                status = "skipped_small" if str(exc).startswith("too small") else "unreadable"
                store.update(conn, sha, status=status, error=str(exc)[:500])
                done[status] += 1
                conn.commit()
                continue
            held, score, classes = screener.check(dest)
            if held:
                dest.unlink(missing_ok=True)  # no sendable copy of a held photo exists
            status = "held_sensitive" if held else "ready"
            store.update(conn, sha, status=status, screen_score=round(score, 4),
                         screen_classes=",".join(classes) or None, error=None, **info)
            done[status] += 1
            conn.commit()
    print(json.dumps(done, sort_keys=True))
    return 0


def cmd_status(cfg: Config, args) -> int:
    with store.connect(cfg.db_path) as conn:
        print(json.dumps(store.counts(conn), sort_keys=True, indent=1))
    return 0


def cmd_held(cfg: Config, args) -> int:
    with store.connect(cfg.db_path) as conn:
        for row in store.by_status(conn, "held_sensitive"):
            print(f"{row['screen_score']:.2f}\t{row['source_path']}")
    return 0


def cmd_check(cfg: Config, args) -> int:
    from .send import check
    out = check()
    print(json.dumps(out, sort_keys=True))
    return 0 if out["ok"] else 3


def cmd_send(cfg: Config, args) -> int:
    from .send import run_batch
    print(json.dumps(run_batch(cfg, args.size, args.budget), sort_keys=True))
    return 0


def cmd_collect(cfg: Config, args) -> int:
    from .send import collect
    print(json.dumps(collect(cfg, args.batch_id), sort_keys=True))
    return 0


def cmd_page(cfg: Config, args) -> int:
    from .render import render
    print(render(cfg))
    return 0


PROGRESS = Path("/var/moo/photo-harvest/progress.json")


def _progress(cfg: Config, state: str, **extra) -> None:
    from .send import spent
    with store.connect(cfg.db_path) as conn:
        body = {"state": state, "ts": int(time.time()), "counts": store.counts(conn),
                "spent_usd": round(spent(conn), 4), **extra}
    tmp = PROGRESS.with_suffix(".tmp")
    tmp.write_text(json.dumps(body, sort_keys=True, indent=1))
    tmp.chmod(0o644)
    tmp.replace(PROGRESS)


def cmd_run(cfg: Config, args) -> int:
    """Alternate prepare and send until no photo is pending or ready.

    Each round prepares up to `chunk` photos, then sends every ready photo in
    batches of `chunk`. Finishes any batch left submitted by an interruption
    first. Stops on the spending stop or on three failed rounds in a row.
    """
    from .send import SendError, collect, run_batch
    with store.connect(cfg.db_path) as conn:
        open_batches = [r[0] for r in conn.execute(
            "SELECT DISTINCT batch_id FROM photo_harvest WHERE status='submitted' AND batch_id IS NOT NULL")]
    for b in open_batches:
        log.info("finishing interrupted batch %s", b)
        collect(cfg, b)
    strikes, rounds = 0, 0
    while True:
        with store.connect(cfg.db_path) as conn:
            c = store.counts(conn)
        if not c.get("pending") and not c.get("ready"):
            break
        rounds += 1
        _progress(cfg, "running", round=rounds)
        try:
            if c.get("pending") and c.get("ready", 0) < args.chunk:
                cmd_prepare(cfg, SimpleNamespace(limit=args.chunk))
            out = run_batch(cfg, args.chunk, args.budget)
            log.info("round %d: %s", rounds, out)
            strikes = 0
        except SendError as exc:  # spending stop: never retried
            log.error("%s", exc)
            _progress(cfg, "stopped", reason=str(exc))
            return 4
        except Exception as exc:  # network, API outage: back off, three strikes
            strikes += 1
            log.exception("round %d failed (%d/3)", rounds, strikes)
            if strikes >= 3:
                _progress(cfg, "failed", reason=f"{type(exc).__name__}: {exc}"[:300])
                return 5
            time.sleep(300 * strikes)
    _progress(cfg, "done", rounds=rounds)
    from .render import render
    render(cfg)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="photo_harvest", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("inventory", "prepare"):
        sp = sub.add_parser(name)
        sp.add_argument("--limit", type=int, default=None)
        if name == "inventory":
            sp.add_argument("--recheck", action="store_true",
                            help="look again for photos marked unreadable")
    sub.add_parser("status")
    sub.add_parser("held")
    sub.add_parser("check")
    sub.add_parser("page")
    sp = sub.add_parser("send")
    sp.add_argument("--size", type=int, default=200)
    sp.add_argument("--budget", type=float, default=20.0, help="spending stop, USD")
    sp = sub.add_parser("run")
    sp.add_argument("--chunk", type=int, default=300)
    sp.add_argument("--budget", type=float, default=20.0, help="spending stop, USD")
    sp = sub.add_parser("collect")
    sp.add_argument("batch_id")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        cfg = Config.from_env()
        return {"inventory": cmd_inventory, "prepare": cmd_prepare,
                "status": cmd_status, "held": cmd_held, "check": cmd_check,
                "send": cmd_send, "collect": cmd_collect, "page": cmd_page,
                "run": cmd_run}[args.cmd](cfg, args)
    except (store.StoreError, ValueError, RuntimeError) as exc:
        log.error("%s", exc)
        return 2
