"""Command line for the Photo Description Harvest. [co-06tcu]

    python -m photo_harvest inventory [--limit N] [--recheck]
    python -m photo_harvest prepare   [--limit N]   # prepare + local screen
    python -m photo_harvest status
    python -m photo_harvest held                   # held photos, by location only
    python -m photo_harvest check                  # one tiny request: key and credit
    python -m photo_harvest send --size 200        # one batch: submit, wait, store, delete
    python -m photo_harvest collect BATCH_ID       # finish a batch after an interruption
    python -m photo_harvest page                   # desk page of described photos

Run from DataArchive/python with its .venv. Every stage resumes from the
status column; Ctrl+C is safe between photos.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

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
    sp = sub.add_parser("collect")
    sp.add_argument("batch_id")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        cfg = Config.from_env()
        return {"inventory": cmd_inventory, "prepare": cmd_prepare,
                "status": cmd_status, "held": cmd_held, "check": cmd_check,
                "send": cmd_send, "collect": cmd_collect, "page": cmd_page}[args.cmd](cfg, args)
    except (store.StoreError, ValueError, RuntimeError) as exc:
        log.error("%s", exc)
        return 2
