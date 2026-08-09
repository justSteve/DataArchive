"""Heartbeats with input assertions. [da-04r]

This enterprise's defining failure is work that fails while every automatic
surface reports green: orphaned backup tars behind an `ok` heartbeat, a semantic
index answering from a twenty-day-stale corpus, a regression test passing against
the code it was written to catch. This module is the countermeasure, and it has
exactly three rules.

1. **A run that found nothing is not a run that never happened.** The heartbeat
   carries the inputs it looked at — entries scanned, files read, corpus age — so
   `candidates: 0` alongside `entries_scanned: 1840` reads as a healthy empty
   pass, while a missing file or an old `ts` reads as a miss. The distinction
   lives in the data instead of being inferred from the absence of a complaint.
2. **An unmet precondition fails loudly.** `Assertion.failed()` forces the run
   status to `degraded` or `failed`. There is no code path that logs "skipping"
   and returns success.
3. **Every status branch has a fail-closed fallback.** An unrecognised status is
   `failed`, never `ok`.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

OK = "ok"
DEGRADED = "degraded"
FAILED = "failed"

_SEVERITY = {OK: 0, DEGRADED: 1, FAILED: 2}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def worst(*statuses: str) -> str:
    """Combine statuses, worst wins. An unknown status is treated as FAILED.

    The fail-closed default is the point: a typo in a status string must never
    resolve to healthy.
    """
    result = OK
    for status in statuses:
        severity = _SEVERITY.get(status)
        if severity is None:
            return FAILED
        if severity > _SEVERITY[result]:
            result = status
    return result


@dataclass
class Assertion:
    """One precondition, its verdict, and the evidence behind the verdict."""

    name: str
    status: str
    detail: str
    observed: Any = None

    def failed(self) -> bool:
        return self.status != OK

    def as_dict(self) -> dict:
        return {"name": self.name, "status": self.status,
                "detail": self.detail, "observed": self.observed}


@dataclass
class RunReport:
    """Accumulates assertions and counters, then writes the heartbeat."""

    job: str
    started: datetime = field(default_factory=utcnow)
    assertions: list[Assertion] = field(default_factory=list)
    counters: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    forced_status: str | None = None

    # --- assertions -----------------------------------------------------------

    def assert_true(self, name: str, condition: bool, detail_ok: str,
                    detail_bad: str, *, severity: str = FAILED,
                    observed: Any = None) -> Assertion:
        assertion = Assertion(
            name=name,
            status=OK if condition else severity,
            detail=detail_ok if condition else detail_bad,
            observed=observed)
        self.assertions.append(assertion)
        return assertion

    def assert_fresh(self, name: str, observed_ts: datetime | None,
                     max_age_seconds: int, *, severity: str = DEGRADED
                     ) -> Assertion:
        """A timestamp must be no older than `max_age_seconds`.

        An unparseable or missing timestamp is a failure of the assertion, not a
        pass — "we could not tell" resolving to "fine" is how a stale corpus
        stays invisible.
        """
        if observed_ts is None:
            return self.assert_true(
                name, False, "", "no timestamp available to check freshness",
                severity=severity, observed=None)
        age = (utcnow() - observed_ts).total_seconds()
        return self.assert_true(
            name, age <= max_age_seconds,
            f"fresh ({int(age)}s old)",
            f"STALE: {int(age)}s old, limit {max_age_seconds}s",
            severity=severity, observed=iso(observed_ts))

    def assert_nonempty(self, name: str, collection: Iterable,
                        *, severity: str = FAILED) -> Assertion:
        items = list(collection)
        return self.assert_true(
            name, bool(items),
            f"{len(items)} found",
            "EMPTY — the inputs this job reads are missing or moved",
            severity=severity, observed=len(items))

    # --- counters and notes ---------------------------------------------------

    def count(self, key: str, value: Any) -> None:
        self.counters[key] = value

    def bump(self, key: str, amount: int = 1) -> None:
        self.counters[key] = int(self.counters.get(key, 0)) + amount

    def note(self, message: str) -> None:
        self.notes.append(message)

    def fail(self, message: str) -> None:
        """Force the run to FAILED with a reason. Used for exceptions."""
        self.forced_status = FAILED
        self.notes.append(message)

    def degrade(self, message: str) -> None:
        self.forced_status = worst(self.forced_status or OK, DEGRADED)
        self.notes.append(message)

    # --- verdict --------------------------------------------------------------

    @property
    def status(self) -> str:
        statuses = [a.status for a in self.assertions]
        if self.forced_status:
            statuses.append(self.forced_status)
        return worst(*statuses) if statuses else OK

    @property
    def failed_assertions(self) -> list[Assertion]:
        return [a for a in self.assertions if a.failed()]

    def exit_code(self) -> int:
        """0 healthy · 1 degraded · 2 failed. Cron reads this."""
        return {OK: 0, DEGRADED: 1, FAILED: 2}.get(self.status, 2)

    def as_dict(self, extra: dict | None = None) -> dict:
        now = utcnow()
        doc = {
            "job": self.job,
            "ts": iso(now),
            "status": self.status,
            "started_at": iso(self.started),
            "duration_ms": int((now - self.started).total_seconds() * 1000),
            "assertions": [a.as_dict() for a in self.assertions],
            "failed_assertions": [a.name for a in self.failed_assertions],
            "counters": self.counters,
            "notes": "; ".join(self.notes),
            "host_pid": os.getpid(),
        }
        if extra:
            doc.update(extra)
        return doc

    def summary_line(self) -> str:
        counters = " · ".join(f"{k}={v}" for k, v in sorted(self.counters.items()))
        failures = ", ".join(a.name for a in self.failed_assertions)
        line = f"{self.job}: {self.status.upper()}"
        if counters:
            line += f" — {counters}"
        if failures:
            line += f" — failed assertions: {failures}"
        if self.notes:
            line += f" — {'; '.join(self.notes)}"
        return line


def write(path: Path, document: dict) -> None:
    """Atomically replace a heartbeat file.

    Atomic because a torn heartbeat read by the next reader is indistinguishable
    from a corrupt one, and this enterprise has already been bitten by torn
    copies that looked like backups.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".hb-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2, sort_keys=False, default=str)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        # mkstemp creates 0600 and os.replace preserves it; every other file in
        # /var/moo/state is 0644 and other tooling reads these.
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read(path: Path) -> dict | None:
    try:
        with Path(path).open(encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, ValueError):
        return None
    return document if isinstance(document, dict) else None


def evaluate(path: Path, stale_after_seconds: int) -> dict:
    """Read a heartbeat and classify it for an operator or a monitoring caller.

    Returns `{state, status, age_seconds, ts, message, document}` where `state` is
    one of `ok`, `degraded`, `failed`, `stale`, `missing`, `unreadable`. Missing
    and stale are distinct from a run that reported nothing, which is the whole
    reason this function exists.
    """
    path = Path(path)
    if not path.exists():
        return {"state": "missing", "status": None, "age_seconds": None,
                "ts": None, "message": f"no heartbeat at {path} — the job has "
                                       "never run, or cannot write its state",
                "document": None}

    document = read(path)
    if document is None:
        return {"state": "unreadable", "status": None, "age_seconds": None,
                "ts": None, "message": f"heartbeat at {path} is not readable JSON",
                "document": None}

    raw_ts = document.get("ts")
    try:
        stamped = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
        if stamped.tzinfo is None:
            stamped = stamped.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return {"state": "unreadable", "status": document.get("status"),
                "age_seconds": None, "ts": raw_ts,
                "message": f"heartbeat at {path} has no parseable ts",
                "document": document}

    age = (utcnow() - stamped).total_seconds()
    if age > stale_after_seconds:
        return {"state": "stale", "status": document.get("status"),
                "age_seconds": int(age), "ts": raw_ts,
                "message": (f"last run {int(age // 3600)}h ago, limit "
                            f"{stale_after_seconds // 3600}h — the job stopped firing"),
                "document": document}

    status = document.get("status")
    if status not in _SEVERITY:  # fail closed on an unrecognised status
        return {"state": "failed", "status": status, "age_seconds": int(age),
                "ts": raw_ts,
                "message": f"unrecognised status {status!r} — treating as failed",
                "document": document}

    return {"state": status, "status": status, "age_seconds": int(age),
            "ts": raw_ts, "message": document.get("notes") or "", "document": document}


def next_due(last_ts: str | None, interval_hours: int) -> str | None:
    if not last_ts:
        return None
    try:
        stamped = datetime.fromisoformat(str(last_ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return iso(stamped + timedelta(hours=interval_hours))
