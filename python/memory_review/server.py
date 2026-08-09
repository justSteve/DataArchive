"""The capture endpoint: where Steve's decisions land. [da-04r]

A loopback-only HTTP service on port 3010 (3000/3001 stay reserved-and-unused
enterprise-wide [co-e591g]; 3002 is Claude Monitor). Stdlib only — no framework —
because this has one job and a dependency here would be a dependency added for
elegance.

Routes:
  GET  /api/health          liveness plus the counts a caller needs to trust it
  GET  /review              the packet page, served same-origin so fetch just works
  GET  /api/packet/latest   the packet as JSON
  POST /api/adjudications   record decisions — the whole reason this exists

Two properties that matter more than the routes:

* **It never reports a success it did not get.** A write that fails returns a
  non-2xx with the reason, and the page turns that into a red banner and a
  downloadable file. A 200 from here means the row is in SQLite *and* the line is
  fsynced to the git-tracked ledger.
* **It writes nothing to any knowledge bundle.** A `graduate` ruling is recorded
  as a proposal. Bundle writes are bead-authorized per `.claude/rules/okf-memory.md`
  and `conventions/log.md` is append-only; a web handler is not on the list of
  things allowed to write shared truth.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import analyze, config, heartbeat, ledger, render
from .store import Store

MAX_BODY_BYTES = 4 * 1024 * 1024  # a packet's worth of decisions, generously


class ReviewHandler(BaseHTTPRequestHandler):
    server_version = "MemoryReview/1.0"
    protocol_version = "HTTP/1.1"

    # --- plumbing -------------------------------------------------------------

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        print(f"{stamp} {self.address_string()} {fmt % args}", flush=True)

    def _cors(self) -> None:
        # The page is opened from file:// (Origin: null) as well as from this
        # server. Loopback bind is the actual access control; CORS here only
        # stops the browser refusing its own page.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, document: dict) -> None:
        self._send(status, json.dumps(document, default=str).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _error(self, status: int, message: str) -> None:
        self.log_message("ERROR %d %s", status, message)
        self._json(status, {"ok": False, "error": message})

    # --- routes ---------------------------------------------------------------

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path.rstrip("/") or "/"
        try:
            if path in ("/api/health", "/health"):
                return self._health()
            if path in ("/", "/review"):
                return self._page()
            if path == "/api/packet/latest":
                return self._latest_packet()
            if path == "/api/ledger/stats":
                return self._json(200, {"ok": True, **ledger.stats()})
            return self._error(404, f"no route {path}")
        except Exception as exc:  # noqa: BLE001 — never leak a bare traceback
            return self._error(500, f"{type(exc).__name__}: {exc}")

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path.rstrip("/") or "/"
        try:
            if path == "/api/adjudications":
                return self._record()
            return self._error(404, f"no route {path}")
        except Exception as exc:  # noqa: BLE001
            return self._error(500, f"{type(exc).__name__}: {exc}")

    # --- handlers -------------------------------------------------------------

    def _open_store(self) -> Store:
        return Store(self.server.db_path)  # type: ignore[attr-defined]

    def _health(self) -> None:
        with self._open_store() as store:
            packet = store.latest_packet()
            collect_hb = heartbeat.evaluate(config.COLLECT_HEARTBEAT,
                                            config.COLLECT_STALE_AFTER_SECONDS)
            packet_hb = heartbeat.evaluate(config.PACKET_HEARTBEAT,
                                           config.PACKET_STALE_AFTER_SECONDS)
            document = {
                "ok": True,
                "service": "memory-review-endpoint",
                "db": str(self.server.db_path),  # type: ignore[attr-defined]
                "started_at": self.server.started_at,  # type: ignore[attr-defined]
                "uptime_seconds": int(time.time() - self.server.started_epoch),  # type: ignore[attr-defined]
                "latest_packet": {
                    "id": packet["id"], "built_at": packet["built_at"],
                    "status": packet["status"], "items": packet["item_count"],
                } if packet else None,
                "adjudications_recorded": len(
                    store.adjudications_for_packet(packet["id"])) if packet else 0,
                "ledger": ledger.stats(),
                "collect_heartbeat": {"state": collect_hb["state"],
                                      "message": collect_hb["message"]},
                "packet_heartbeat": {"state": packet_hb["state"],
                                     "message": packet_hb["message"]},
            }
        self._json(200, document)

    def _page(self) -> None:
        with self._open_store() as store:
            packet = store.latest_packet()
            if packet is None:
                return self._send(
                    503,
                    ("<h1>No packet has been built yet</h1><p>Run "
                     "<code>python3 -m memory_review packet</code> first. This is "
                     "not an empty review — it is the absence of one.</p>"
                     ).encode("utf-8"),
                    "text/html; charset=utf-8")
            payload = analyze.packet_payload(store, packet["id"])
        markup = render.render(payload)
        self._send(200, markup.encode("utf-8"), "text/html; charset=utf-8")

    def _latest_packet(self) -> None:
        with self._open_store() as store:
            packet = store.latest_packet()
            if packet is None:
                return self._error(404, "no packet has been built yet")
            payload = analyze.packet_payload(store, packet["id"])
        self._json(200, payload)

    def _record(self) -> None:
        length_header = self.headers.get("Content-Length")
        try:
            length = int(length_header or 0)
        except ValueError:
            return self._error(400, f"unreadable Content-Length {length_header!r}")
        if length <= 0:
            return self._error(400, "empty request body")
        if length > MAX_BODY_BYTES:
            return self._error(413, f"body of {length} bytes exceeds {MAX_BODY_BYTES}")

        try:
            document = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            return self._error(400, f"body is not valid JSON: {exc}")
        if not isinstance(document, dict):
            return self._error(400, "body must be a JSON object")

        result = apply_submission(document, db_path=self.server.db_path)  # type: ignore[attr-defined]
        if not result.get("ok"):
            return self._error(int(result.pop("status", 400)), result.get("error", ""))
        self._json(200, result)


def apply_submission(document: dict, db_path: Path | str | None = None) -> dict:
    """Validate and record one submission. Shared by the endpoint and the CLI import.

    Returns a result dict; `ok: False` carries `status` and `error`. Every failure
    path is explicit — there is no branch that swallows a bad decision and returns
    a cheerful 200, because a page that says "recorded" over a dropped write is the
    exact defect this pipeline was told not to reproduce.
    """
    packet_id = document.get("packet_id")
    if not isinstance(packet_id, int):
        return {"ok": False, "status": 400,
                "error": f"packet_id must be an integer, got {packet_id!r}"}

    decisions = document.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        return {"ok": False, "status": 400,
                "error": "decisions must be a non-empty array"}

    client_id = document.get("client_id")
    if client_id is not None and not isinstance(client_id, str):
        return {"ok": False, "status": 400, "error": "client_id must be a string"}

    with Store(db_path) as store:
        packet = store.packet(packet_id)
        if packet is None:
            return {"ok": False, "status": 404,
                    "error": f"no packet {packet_id} in this store — the page may "
                             "be from a different machine or an older database"}

        known = {row["dedupe_key"]: row for row in store.packet_items(packet_id)}

        # Validate the whole batch before writing any of it. A half-applied
        # submission is worse than a rejected one: the page cannot tell which
        # half landed.
        prepared = []
        for index, raw in enumerate(decisions):
            if not isinstance(raw, dict):
                return {"ok": False, "status": 400,
                        "error": f"decisions[{index}] is not an object"}
            key = raw.get("dedupe_key")
            if not isinstance(key, str) or not key:
                return {"ok": False, "status": 400,
                        "error": f"decisions[{index}] has no dedupe_key"}
            if key not in known:
                return {"ok": False, "status": 400,
                        "error": f"decisions[{index}] references {key!r}, which is "
                                 f"not an item of packet {packet_id}"}
            decision = raw.get("decision")
            if decision not in ledger.DECISIONS:
                return {"ok": False, "status": 400,
                        "error": f"decisions[{index}] has decision {decision!r}; "
                                 f"expected one of {', '.join(ledger.DECISIONS)}"}
            note = raw.get("note")
            if note is not None and not isinstance(note, str):
                return {"ok": False, "status": 400,
                        "error": f"decisions[{index}] note must be a string"}
            if decision == "discard" and not (note or "").strip():
                return {"ok": False, "status": 400,
                        "error": f"decisions[{index}] discards {key!r} with no "
                                 "reason. A tombstone without a reason is a booby "
                                 "trap for whoever inherits it — say why."}
            prepared.append((key, decision, note, raw.get("decided_at"),
                             known[key]))

        inserted = updated = 0
        ledger_entries = []
        for key, decision, note, decided_at, item in prepared:
            verdict = store.record_adjudication(
                packet_id=packet_id, dedupe_key=key, section=item["section"],
                decision=decision, note=note,
                decided_at=decided_at or ledger.utcnow(), client_id=client_id,
                source=document.get("source") or "desk-form")
            if verdict == "inserted":
                inserted += 1
            elif verdict == "updated":
                updated += 1
            else:  # fail closed on an unrecognised verdict
                return {"ok": False, "status": 500,
                        "error": f"store returned unknown verdict {verdict!r}"}

            ledger_entries.append(ledger.record(
                packet_id=packet_id, dedupe_key=key, section=item["section"],
                decision=decision, note=note, decided_at=decided_at,
                headline=item["headline"], source_ref=item["source_ref"],
                anchor_class=item["anchor_class"], client_id=client_id,
                source=document.get("source") or "desk-form"))

            if decision == "discard":
                store.add_tombstone(key, item["headline"] + "\n" + (item["body"] or ""),
                                    (note or "").strip())

        try:
            ledger.append(ledger_entries)
        except OSError as exc:
            # The store has the rows but git will not carry them. Say so loudly
            # rather than returning a clean success.
            return {"ok": False, "status": 500,
                    "error": f"decisions were written to the store but the "
                             f"git-tracked ledger write FAILED: {exc}. Re-run this "
                             "submission once the ledger path is writable."}

        # Advance the review window ONLY when every item in the packet has been
        # ruled on. Advancing on any submission would mean answering five of
        # seventy-one items silently discarded the other sixty-six from the next
        # packet's "new since last review" window — work vanishing because it was
        # partly done, which is the shape of failure this pipeline exists to
        # stop making.
        answered = {row["dedupe_key"] for row in store.adjudications_for_packet(packet_id)}
        outstanding = [row["dedupe_key"] for row in store.packet_items(packet_id)
                       if row["dedupe_key"] not in answered]
        if not outstanding:
            analyze.mark_reviewed(store)
        stats = ledger.stats()
        proposals = [e for e in ledger_entries if e["decision"] == "graduate"]

    return {
        "ok": True,
        "packet_id": packet_id,
        "recorded": inserted + updated,
        "inserted": inserted,
        "updated": updated,
        "outstanding": len(outstanding),
        "packet_complete": not outstanding,
        "ledger_entries": stats["entries"],
        "graduation_proposals": len(proposals),
        "note": "Recorded as proposals. Nothing here wrote to a knowledge bundle — "
                "a bundle write needs a bead.",
    }


def serve(host: str | None = None, port: int | None = None,
          db_path: Path | str | None = None,
          heartbeat_interval: int = 300) -> None:
    """Run the endpoint until interrupted. Writes a heartbeat while it lives.

    The heartbeat is what makes the endpoint's absence detectable: `state:
    "stale"` on `memory-review-endpoint-heartbeat.json` means the process died,
    which is a different diagnosis from "no decisions were submitted today".
    """
    host = host or config.ENDPOINT_HOST
    port = port if port is not None else config.ENDPOINT_PORT
    db_path = Path(db_path) if db_path else config.DB_PATH
    config.ensure_dirs()

    server = ThreadingHTTPServer((host, port), ReviewHandler)
    server.db_path = db_path                       # type: ignore[attr-defined]
    server.started_epoch = time.time()             # type: ignore[attr-defined]
    server.started_at = datetime.now(timezone.utc).strftime(  # type: ignore[attr-defined]
        "%Y-%m-%dT%H:%M:%SZ")
    server.daemon_threads = True

    stopping = threading.Event()

    def beat() -> None:
        while not stopping.wait(0):
            report = heartbeat.RunReport(job="memory-review-endpoint")
            try:
                with Store(db_path) as store:
                    packet = store.latest_packet()
                    report.assert_true(
                        "store_readable", True, "store opened", "")
                    report.count("latest_packet_id", packet["id"] if packet else None)
                    report.count("adjudications", len(
                        store.adjudications_for_packet(packet["id"])) if packet else 0)
                report.count("ledger", ledger.stats())
                report.count("listening", f"http://{host}:{port}")
            except Exception as exc:  # noqa: BLE001
                report.fail(f"endpoint self-check failed: {type(exc).__name__}: {exc}")
            try:
                heartbeat.write(config.ENDPOINT_HEARTBEAT, report.as_dict())
            except OSError as exc:
                print(f"memory-review endpoint: heartbeat write failed: {exc}",
                      flush=True)
            if stopping.wait(heartbeat_interval):
                return

    beater = threading.Thread(target=beat, name="heartbeat", daemon=True)
    beater.start()

    print(f"memory-review endpoint listening on http://{host}:{port} "
          f"(db {db_path})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("memory-review endpoint: interrupted, shutting down", flush=True)
    finally:
        stopping.set()
        server.shutdown()
        server.server_close()
        final = heartbeat.RunReport(job="memory-review-endpoint")
        final.degrade("endpoint stopped — no capture path until it is restarted")
        try:
            heartbeat.write(config.ENDPOINT_HEARTBEAT, final.as_dict())
        except OSError:
            pass
