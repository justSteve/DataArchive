"""Append-only, git-tracked record of every adjudication. [da-04r]

`data/` is gitignored in this repo, so the SQLite store is local-only by design.
An adjudication is the one artifact in this pipeline that cannot be regenerated —
rebuild the packet and you get the same candidates back, but Steve's ruling on
them exists nowhere else. So it is written twice: to the store, for the pipeline
to query, and to this ledger, for git to carry off the box.

Append-only in the same sense as `conventions/log.md`: a changed answer appends a
new line, it does not rewrite the old one. Replaying the file newest-line-wins
reconstructs current state, and the history of a changed mind stays visible.

This file records what Steve decided. It does **not** act on those decisions —
nothing here writes to an OKF bundle. Bundle writes are bead-authorized per
`.claude/rules/okf-memory.md`, and a `graduate` ruling recorded here is a
proposal for a bead, not a commit.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

from . import config

DECISIONS = ("confirm", "correct", "discard", "graduate", "defer")

DECISION_MEANINGS = {
    "confirm": "Right as written. Leave it alone.",
    "correct": "Nearly right, or wrongly framed. The note carries the correction.",
    "discard": "Wrong. Tombstone it so it stops coming back.",
    "graduate": "Worth promoting into curated truth — files a proposal, never a write.",
    "defer": "Not now. It returns in the next packet.",
}


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append(entries: Iterable[dict], path: Path | None = None) -> int:
    """Append adjudication records. Returns the count written.

    Writes are flushed and fsynced before returning: a caller that has been told
    the ruling is recorded must not lose it to a power cut. A write failure
    raises — the endpoint turns that into an error the page displays, rather than
    a silent 200 that leaves Steve believing his answers were saved.
    """
    path = Path(path) if path else config.ADJUDICATION_LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with path.open("a", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry, separators=(",", ":"), sort_keys=True) + "\n")
            written += 1
        handle.flush()
        os.fsync(handle.fileno())
    return written


def record(*, packet_id: int, dedupe_key: str, section: str | None,
           decision: str, note: str | None, decided_at: str | None,
           headline: str | None = None, source_ref: str | None = None,
           anchor_class: str | None = None, client_id: str | None = None,
           source: str = "desk-form") -> dict:
    """Build one ledger entry, validating the decision vocabulary.

    An unrecognised decision raises rather than being stored as-is: a decision
    string nothing understands is a row that every later reader will silently
    skip, which is the shape of failure this pipeline was built to stop making.
    """
    if decision not in DECISIONS:
        raise ValueError(
            f"unknown decision {decision!r}; expected one of {', '.join(DECISIONS)}")
    return {
        "ts": utcnow(),
        "packet_id": packet_id,
        "dedupe_key": dedupe_key,
        "section": section,
        "anchor_class": anchor_class,
        "decision": decision,
        "note": (note or "").strip() or None,
        "decided_at": decided_at or utcnow(),
        "headline": headline,
        "source_ref": source_ref,
        "client_id": client_id,
        "source": source,
    }


def replay(path: Path | None = None) -> dict[tuple[int, str], dict]:
    """Current state from the ledger: newest line wins per (packet, item).

    Used to rebuild the store after a data-directory loss, and as the
    cross-check that the store and the ledger agree.
    """
    path = Path(path) if path else config.ADJUDICATION_LEDGER
    state: dict[tuple[int, str], dict] = {}
    for entry in iter_entries(path):
        key = (entry.get("packet_id"), entry.get("dedupe_key"))
        if key[0] is None or key[1] is None:
            continue
        state[key] = entry
    return state


def iter_entries(path: Path | None = None) -> Iterator[dict]:
    """Yield every well-formed ledger entry, counting the malformed ones aloud."""
    path = Path(path) if path else config.ADJUDICATION_LEDGER
    if not path.exists():
        return
    malformed = 0
    with path.open(encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                malformed += 1
                print(f"memory-review ledger: line {lineno} of {path} is not JSON",
                      flush=True)
                continue
            if isinstance(entry, dict):
                yield entry
            else:
                malformed += 1
    if malformed:
        print(f"memory-review ledger: {malformed} unreadable line(s) in {path}",
              flush=True)


def stats(path: Path | None = None) -> dict:
    counts: dict[str, int] = {}
    packets: set[int] = set()
    total = 0
    for entry in iter_entries(path):
        total += 1
        decision = entry.get("decision") or "unknown"
        counts[decision] = counts.get(decision, 0) + 1
        if isinstance(entry.get("packet_id"), int):
            packets.add(entry["packet_id"])
    return {"entries": total, "decisions": counts, "packets_reviewed": len(packets)}
