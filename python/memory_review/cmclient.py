"""Claude Monitor HTTP client with per-request traffic logging. [da-04r]

Every call CM serves this pipeline is recorded — endpoint, parameters, status,
duration, byte count, row count. Steve named the traffic log as a *purpose* of
this pipeline, not a side effect: the gaps in what CM can answer are only
findable if the asking is written down.

Two rules this module exists to enforce:

1. A request that fails raises. It never returns an empty list that a caller
   could mistake for "CM had nothing". `CMUnavailable` and `CMRequestError` are
   distinct so a caller can tell "the service is down" from "the service said
   no".
2. Every request is logged whether it succeeded or not. A gap in the traffic log
   means the process died, and that is a different diagnosis from a logged 500.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from . import config


class CMError(RuntimeError):
    """Base class for every Claude Monitor failure."""


class CMUnavailable(CMError):
    """CM could not be reached at all — connection refused, DNS, timeout."""


class CMRequestError(CMError):
    """CM answered, with a status this client will not treat as success."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


@dataclass
class TrafficRecord:
    """One CM request, as it will appear in the traffic log."""

    ts: str
    method: str
    path: str
    params: dict
    status: int | None
    ok: bool
    duration_ms: int
    bytes_in: int
    rows: int | None
    error: str | None
    run_id: int | None = None

    def as_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class TrafficLog:
    """Append-only JSONL sink for CM traffic, one file per UTC day.

    A failure to write the traffic log is reported to stderr but does not abort
    the run: losing observability is bad, losing the collection because
    observability broke is worse. The failure is counted and surfaced in the
    heartbeat so it cannot pass unnoticed.
    """

    def __init__(self, log_dir: Path | None = None):
        self.log_dir = Path(log_dir) if log_dir else config.MOO_LOG_DIR
        self.write_failures = 0
        self.records: list[TrafficRecord] = []

    def path_for(self, ts: str) -> Path:
        return self.log_dir / f"cm-traffic-{ts[:10]}.jsonl"

    def append(self, record: TrafficRecord) -> None:
        self.records.append(record)
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            with self.path_for(record.ts).open("a", encoding="utf-8") as handle:
                handle.write(record.as_json() + "\n")
        except OSError as exc:
            self.write_failures += 1
            print(f"memory-review: traffic log write failed: {exc}", flush=True)

    def summary(self) -> dict:
        total = len(self.records)
        failed = sum(1 for r in self.records if not r.ok)
        duration = sum(r.duration_ms for r in self.records)
        return {
            "requests": total,
            "failed": failed,
            "bytes_in": sum(r.bytes_in for r in self.records),
            "total_ms": duration,
            "log_write_failures": self.write_failures,
        }


class CMClient:
    """Read-only client for Claude Monitor's v1 API."""

    def __init__(self,
                 base_url: str | None = None,
                 timeout: int | None = None,
                 traffic_log: TrafficLog | None = None,
                 opener: Callable[..., Any] | None = None):
        self.base_url = (base_url or config.CM_BASE_URL).rstrip("/")
        self.timeout = timeout if timeout is not None else config.CM_TIMEOUT_SECONDS
        self.traffic = traffic_log if traffic_log is not None else TrafficLog()
        self._opener = opener or urllib.request.urlopen
        self.run_id: int | None = None

    # --- transport ------------------------------------------------------------

    def _get(self, path: str, params: dict | None = None,
             row_key: str | None = "data") -> Any:
        params = params or {}
        query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{self.base_url}{path}" + (f"?{query}" if query else "")

        started = time.monotonic()
        status: int | None = None
        payload: bytes = b""
        error: str | None = None
        parsed: Any = None
        rows: int | None = None

        try:
            with self._opener(url, timeout=self.timeout) as response:
                status = getattr(response, "status", None) or response.getcode()
                payload = response.read()
        except urllib.error.HTTPError as exc:
            status = exc.code
            try:
                payload = exc.read()
            except Exception:  # noqa: BLE001 - body is best-effort diagnostic only
                payload = b""
            error = f"HTTP {exc.code}: {payload[:300].decode('utf-8', 'replace')}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            error = f"unreachable: {exc}"
        except Exception as exc:  # noqa: BLE001 - unexpected transport failure
            error = f"transport error: {type(exc).__name__}: {exc}"

        if error is None:
            try:
                parsed = json.loads(payload.decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as exc:
                error = f"malformed JSON from {path}: {exc}"

        if error is None and row_key and isinstance(parsed, dict):
            container = parsed.get(row_key)
            if isinstance(container, list):
                rows = len(container)

        duration_ms = int((time.monotonic() - started) * 1000)
        self.traffic.append(TrafficRecord(
            ts=_utcnow(), method="GET", path=path, params=params,
            status=status, ok=error is None, duration_ms=duration_ms,
            bytes_in=len(payload), rows=rows, error=error, run_id=self.run_id,
        ))

        if error is not None:
            if status is None:
                raise CMUnavailable(f"GET {path}: {error}")
            raise CMRequestError(f"GET {path}: {error}", status=status)

        return parsed

    # --- API surface ----------------------------------------------------------

    def health(self) -> dict:
        """CM's own health document. Raises if CM cannot answer."""
        result = self._get("/api/v1/health", row_key=None)
        if not isinstance(result, dict):
            raise CMRequestError(f"/api/v1/health returned {type(result).__name__}, expected object")
        return result

    def corpus_freshness(self) -> tuple[datetime | None, dict]:
        """(timestamp of CM's most recent ingested entry, raw health doc).

        The timestamp is the input assertion that matters most: a pipeline that
        clusters a corpus which stopped growing twenty days ago is the MemPalace
        defect, and it reports green the whole time.
        """
        doc = self.health()
        raw = doc.get("lastEntryTimestamp")
        if not raw:
            return None, doc
        return parse_cm_timestamp(raw), doc

    def conversations_since(self, since_iso: str, limit: int | None = None) -> list[dict]:
        """Conversations with activity at or after `since_iso`, newest first.

        Pages until an EMPTY page, not until a short one. CM silently caps
        `limit` at its own `maxPageSize` (100), so "a page shorter than I asked
        for means the end" truncated a 50-day window to its first 100
        conversations and reported success. Measured 2026-08-09 while building
        this: 100 returned for a window that holds far more. Stopping only on
        zero costs one extra request per walk and cannot truncate.
        """
        page_size = limit or config.CM_PAGE_SIZE
        out: list[dict] = []
        page = 1
        while True:
            body = self._get("/api/v1/conversations",
                             {"since": since_iso, "page": page, "limit": page_size})
            batch = body.get("data") if isinstance(body, dict) else None
            if not isinstance(batch, list):
                raise CMRequestError(
                    f"/api/v1/conversations page {page} had no 'data' array")
            if not batch:
                return out
            out.extend(batch)
            page += 1
            if page > 500:  # runaway guard; 500 pages is 50k conversations
                raise CMRequestError(
                    "conversations pagination exceeded 500 pages — refusing to loop")

    def conversation_entries(self, conversation_id: int, role: str | None = None
                             ) -> Iterator[dict]:
        """Every entry in one conversation, oldest first, paged.

        Same empty-page rule as `conversations_since`, for the same reason.
        """
        page = 1
        page_size = config.CM_PAGE_SIZE
        while True:
            body = self._get(f"/api/v1/conversations/{conversation_id}/entries",
                             {"role": role, "page": page, "limit": page_size})
            batch = body.get("data") if isinstance(body, dict) else None
            if not isinstance(batch, list):
                raise CMRequestError(
                    f"entries for conversation {conversation_id} had no 'data' array")
            if not batch:
                return
            yield from batch
            page += 1
            if page > 2000:
                raise CMRequestError(
                    f"entries pagination for conversation {conversation_id} "
                    "exceeded 2000 pages — refusing to loop")

    def unified_search(self, query: str, limit: int = 5,
                       signals: str | None = None) -> dict:
        """CM's fused search. Used for the 'does the bundle already say this?' leg."""
        return self._get("/api/v1/search/unified",
                         {"q": query, "limit": limit, "signals": signals},
                         row_key="results")


def parse_cm_timestamp(raw: str) -> datetime | None:
    """Parse the several timestamp shapes CM emits into an aware UTC datetime.

    CM writes `2026-08-09T15:58:01.000Z` in some places and `2026-08-09 15:58:01`
    in others. Returning None for an unrecognised shape is deliberate: the caller
    treats an unparseable freshness stamp as a degraded input assertion rather
    than assuming it is fresh.
    """
    if not raw or not isinstance(raw, str):
        return None
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    candidates = (text, text.replace(" ", "T"))
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None
