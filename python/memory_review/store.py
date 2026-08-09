"""SQLite store for the memory review pipeline. [da-04r]

The operational record: collection runs, the utterance corpus, memory items,
instruction passages, built packets, Steve's adjudications and the CM traffic
index. `data/` is gitignored in this repo, so this database is local-only by
design — the git-visible durable copy of every adjudication is the JSONL ledger
written alongside it (see `ledger.py`).

Schema is applied idempotently on every open. There is no migration runner: the
table set is additive and `CREATE TABLE IF NOT EXISTS` plus explicit
`_add_column_if_missing` covers everything this pipeline has needed.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS collection_runs (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    kind                  TEXT NOT NULL,               -- collect | packet
    started_at            TEXT NOT NULL,
    finished_at           TEXT,
    status                TEXT,                        -- ok | degraded | failed
    cursor_from           TEXT,
    cursor_to             TEXT,
    conversations_seen    INTEGER NOT NULL DEFAULT 0,
    entries_fetched       INTEGER NOT NULL DEFAULT 0,
    utterances_extracted  INTEGER NOT NULL DEFAULT 0,
    utterances_new        INTEGER NOT NULL DEFAULT 0,
    memory_files_seen     INTEGER NOT NULL DEFAULT 0,
    memory_files_changed  INTEGER NOT NULL DEFAULT 0,
    instruction_files_seen INTEGER NOT NULL DEFAULT 0,
    assertions_json       TEXT,
    notes                 TEXT,
    error                 TEXT
);

CREATE TABLE IF NOT EXISTS utterances (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL,
    cm_conversation_id   INTEGER,
    cm_conversation_uuid TEXT,
    project         TEXT,
    entry_index     INTEGER,
    role            TEXT NOT NULL,
    ts              TEXT,
    day             TEXT,
    content         TEXT NOT NULL,
    content_hash    TEXT NOT NULL UNIQUE,
    char_len        INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_utterances_day ON utterances(day);
CREATE INDEX IF NOT EXISTS idx_utterances_conv ON utterances(cm_conversation_id);

CREATE TABLE IF NOT EXISTS memory_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    kind            TEXT NOT NULL,        -- auto-memory | okf-concept
    item_key        TEXT NOT NULL UNIQUE, -- kind + absolute path
    repo            TEXT,
    source_path     TEXT NOT NULL,
    title           TEXT,
    description     TEXT,
    frontmatter_json TEXT,
    body            TEXT NOT NULL,
    body_hash       TEXT NOT NULL,
    mtime           TEXT,
    first_seen_run  INTEGER NOT NULL,
    first_seen_at   TEXT NOT NULL,
    last_seen_run   INTEGER NOT NULL,
    last_seen_at    TEXT NOT NULL,
    changed_at      TEXT,
    removed_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_memory_items_kind ON memory_items(kind);
CREATE INDEX IF NOT EXISTS idx_memory_items_changed ON memory_items(changed_at);

CREATE TABLE IF NOT EXISTS instruction_passages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    repo            TEXT NOT NULL,
    path            TEXT NOT NULL,
    heading         TEXT,
    start_line      INTEGER NOT NULL,
    end_line        INTEGER NOT NULL,
    text            TEXT NOT NULL,
    text_hash       TEXT NOT NULL,
    run_id          INTEGER NOT NULL,
    UNIQUE(path, start_line, text_hash)
);
CREATE INDEX IF NOT EXISTS idx_passages_repo ON instruction_passages(repo);

CREATE TABLE IF NOT EXISTS packets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    built_at        TEXT NOT NULL,
    window_from     TEXT,
    window_to       TEXT,
    status          TEXT NOT NULL,       -- ok | degraded | failed
    degraded_reason TEXT,
    item_count      INTEGER NOT NULL DEFAULT 0,
    thresholds_json TEXT,
    stats_json      TEXT,
    page_path       TEXT,
    run_id          INTEGER
);

CREATE TABLE IF NOT EXISTS packet_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    packet_id       INTEGER NOT NULL,
    section         TEXT NOT NULL,       -- new_memory | collision | contradiction | graduation_candidate
    dedupe_key      TEXT NOT NULL,
    anchor_class    TEXT NOT NULL,       -- steve_stated | coo_inference | not_applicable
    headline        TEXT NOT NULL,
    body            TEXT,
    source_ref      TEXT,
    evidence_json   TEXT,
    score           REAL,
    UNIQUE(packet_id, dedupe_key)
);
CREATE INDEX IF NOT EXISTS idx_packet_items_packet ON packet_items(packet_id);

CREATE TABLE IF NOT EXISTS adjudications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    packet_id       INTEGER NOT NULL,
    dedupe_key      TEXT NOT NULL,
    section         TEXT,
    decision        TEXT NOT NULL,       -- confirm | correct | discard | graduate | defer
    note            TEXT,
    decided_at      TEXT NOT NULL,
    recorded_at     TEXT NOT NULL,
    client_id       TEXT,
    source          TEXT NOT NULL DEFAULT 'desk-form',
    UNIQUE(packet_id, dedupe_key)
);
CREATE INDEX IF NOT EXISTS idx_adjudications_decision ON adjudications(decision);

CREATE TABLE IF NOT EXISTS tombstones (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    dedupe_key      TEXT NOT NULL,
    centroid_text   TEXT NOT NULL,
    reason          TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    suppressed_count INTEGER NOT NULL DEFAULT 0,
    last_suppressed_at TEXT,
    cleared_at      TEXT,
    UNIQUE(dedupe_key)
);

CREATE TABLE IF NOT EXISTS cm_traffic (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER,
    ts              TEXT NOT NULL,
    method          TEXT NOT NULL,
    path            TEXT NOT NULL,
    params_json     TEXT,
    status          INTEGER,
    ok              INTEGER NOT NULL,
    duration_ms     INTEGER NOT NULL,
    bytes_in        INTEGER NOT NULL,
    rows            INTEGER,
    error           TEXT
);
CREATE INDEX IF NOT EXISTS idx_cm_traffic_ts ON cm_traffic(ts);
CREATE INDEX IF NOT EXISTS idx_cm_traffic_ok ON cm_traffic(ok);

CREATE TABLE IF NOT EXISTS cursors (
    name            TEXT PRIMARY KEY,
    value           TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Store:
    """Thin, explicit SQLite wrapper. No ORM, no lazy connections."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else config.DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), timeout=30.0)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    # --- cursors --------------------------------------------------------------

    def get_cursor(self, name: str) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM cursors WHERE name = ?", (name,)).fetchone()
        return row["value"] if row else None

    def set_cursor(self, name: str, value: str) -> None:
        with self.tx() as conn:
            conn.execute(
                "INSERT INTO cursors(name, value, updated_at) VALUES(?,?,?) "
                "ON CONFLICT(name) DO UPDATE SET value=excluded.value, "
                "updated_at=excluded.updated_at",
                (name, value, utcnow()))

    # --- runs -----------------------------------------------------------------

    def start_run(self, kind: str, cursor_from: str | None) -> int:
        with self.tx() as conn:
            cur = conn.execute(
                "INSERT INTO collection_runs(kind, started_at, cursor_from) VALUES(?,?,?)",
                (kind, utcnow(), cursor_from))
            return int(cur.lastrowid)

    def finish_run(self, run_id: int, **fields: Any) -> None:
        allowed = {
            "status", "cursor_to", "conversations_seen", "entries_fetched",
            "utterances_extracted", "utterances_new", "memory_files_seen",
            "memory_files_changed", "instruction_files_seen", "assertions_json",
            "notes", "error",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"finish_run got unknown fields: {sorted(unknown)}")
        fields["finished_at"] = utcnow()
        assignments = ", ".join(f"{k} = ?" for k in fields)
        with self.tx() as conn:
            conn.execute(f"UPDATE collection_runs SET {assignments} WHERE id = ?",
                         (*fields.values(), run_id))

    def last_run(self, kind: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM collection_runs WHERE kind = ? ORDER BY id DESC LIMIT 1",
            (kind,)).fetchone()

    # --- utterances -----------------------------------------------------------

    def insert_utterances(self, run_id: int, rows: Iterable[dict]) -> int:
        inserted = 0
        with self.tx() as conn:
            for row in rows:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO utterances"
                    "(run_id, cm_conversation_id, cm_conversation_uuid, project,"
                    " entry_index, role, ts, day, content, content_hash, char_len)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (run_id, row.get("cm_conversation_id"),
                     row.get("cm_conversation_uuid"), row.get("project"),
                     row.get("entry_index"), row["role"], row.get("ts"),
                     (row.get("ts") or "")[:10] or None, row["content"],
                     row["content_hash"], len(row["content"])))
                inserted += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        return inserted

    def utterances_since(self, since_day: str | None = None) -> list[sqlite3.Row]:
        if since_day:
            return self.conn.execute(
                "SELECT * FROM utterances WHERE day >= ? ORDER BY ts",
                (since_day,)).fetchall()
        return self.conn.execute("SELECT * FROM utterances ORDER BY ts").fetchall()

    def utterance_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) c FROM utterances").fetchone()["c"])

    # --- memory items ---------------------------------------------------------

    def upsert_memory_item(self, run_id: int, item: dict) -> str:
        """Returns 'new', 'changed' or 'unchanged'."""
        now = utcnow()
        existing = self.conn.execute(
            "SELECT id, body_hash FROM memory_items WHERE item_key = ?",
            (item["item_key"],)).fetchone()
        with self.tx() as conn:
            if existing is None:
                conn.execute(
                    "INSERT INTO memory_items(kind, item_key, repo, source_path,"
                    " title, description, frontmatter_json, body, body_hash, mtime,"
                    " first_seen_run, first_seen_at, last_seen_run, last_seen_at, changed_at)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (item["kind"], item["item_key"], item.get("repo"),
                     item["source_path"], item.get("title"), item.get("description"),
                     json.dumps(item.get("frontmatter") or {}), item["body"],
                     item["body_hash"], item.get("mtime"), run_id, now, run_id, now, now))
                return "new"
            if existing["body_hash"] != item["body_hash"]:
                conn.execute(
                    "UPDATE memory_items SET title=?, description=?, frontmatter_json=?,"
                    " body=?, body_hash=?, mtime=?, last_seen_run=?, last_seen_at=?,"
                    " changed_at=?, removed_at=NULL WHERE id=?",
                    (item.get("title"), item.get("description"),
                     json.dumps(item.get("frontmatter") or {}), item["body"],
                     item["body_hash"], item.get("mtime"), run_id, now, now,
                     existing["id"]))
                return "changed"
            conn.execute(
                "UPDATE memory_items SET last_seen_run=?, last_seen_at=?, removed_at=NULL"
                " WHERE id=?", (run_id, now, existing["id"]))
            return "unchanged"

    def mark_missing_memory_items(self, run_id: int, kinds: Iterable[str]) -> int:
        """Tombstone items not seen in this run — a deleted card is a finding."""
        now = utcnow()
        placeholders = ",".join("?" for _ in kinds)
        with self.tx() as conn:
            cur = conn.execute(
                f"UPDATE memory_items SET removed_at = ? "
                f"WHERE kind IN ({placeholders}) AND last_seen_run < ? AND removed_at IS NULL",
                (now, *kinds, run_id))
            return cur.rowcount or 0

    def memory_items(self, kind: str | None = None,
                     include_removed: bool = False) -> list[sqlite3.Row]:
        clauses, params = [], []
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if not include_removed:
            clauses.append("removed_at IS NULL")
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        return self.conn.execute(
            f"SELECT * FROM memory_items{where} ORDER BY item_key", params).fetchall()

    def memory_items_changed_since(self, since_iso: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM memory_items WHERE removed_at IS NULL AND changed_at >= ?"
            " ORDER BY changed_at DESC", (since_iso,)).fetchall()

    # --- instruction passages -------------------------------------------------

    def replace_instruction_passages(self, run_id: int, rows: Iterable[dict]) -> int:
        count = 0
        with self.tx() as conn:
            conn.execute("DELETE FROM instruction_passages")
            for row in rows:
                conn.execute(
                    "INSERT OR IGNORE INTO instruction_passages"
                    "(repo, path, heading, start_line, end_line, text, text_hash, run_id)"
                    " VALUES(?,?,?,?,?,?,?,?)",
                    (row["repo"], row["path"], row.get("heading"), row["start_line"],
                     row["end_line"], row["text"], row["text_hash"], run_id))
                count += 1
        return count

    def instruction_passages(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM instruction_passages ORDER BY repo, path, start_line").fetchall()

    # --- packets --------------------------------------------------------------

    def create_packet(self, *, window_from: str | None, window_to: str | None,
                      status: str, degraded_reason: str | None,
                      thresholds: dict, stats: dict, run_id: int | None) -> int:
        with self.tx() as conn:
            cur = conn.execute(
                "INSERT INTO packets(built_at, window_from, window_to, status,"
                " degraded_reason, thresholds_json, stats_json, run_id)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (utcnow(), window_from, window_to, status, degraded_reason,
                 json.dumps(thresholds), json.dumps(stats), run_id))
            return int(cur.lastrowid)

    def add_packet_items(self, packet_id: int, items: Iterable[dict]) -> int:
        count = 0
        with self.tx() as conn:
            for item in items:
                conn.execute(
                    "INSERT OR REPLACE INTO packet_items"
                    "(packet_id, section, dedupe_key, anchor_class, headline, body,"
                    " source_ref, evidence_json, score) VALUES(?,?,?,?,?,?,?,?,?)",
                    (packet_id, item["section"], item["dedupe_key"],
                     item["anchor_class"], item["headline"], item.get("body"),
                     item.get("source_ref"), json.dumps(item.get("evidence") or {}),
                     item.get("score")))
                count += 1
            conn.execute("UPDATE packets SET item_count = ? WHERE id = ?",
                         (count, packet_id))
        return count

    def set_packet_page(self, packet_id: int, page_path: str) -> None:
        with self.tx() as conn:
            conn.execute("UPDATE packets SET page_path = ? WHERE id = ?",
                         (page_path, packet_id))

    def latest_packet(self) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM packets ORDER BY id DESC LIMIT 1").fetchone()

    def packet(self, packet_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM packets WHERE id = ?", (packet_id,)).fetchone()

    def packet_items(self, packet_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM packet_items WHERE packet_id = ? ORDER BY section, id",
            (packet_id,)).fetchall()

    # --- adjudications --------------------------------------------------------

    def record_adjudication(self, *, packet_id: int, dedupe_key: str,
                            section: str | None, decision: str, note: str | None,
                            decided_at: str, client_id: str | None,
                            source: str = "desk-form") -> str:
        """Upsert one decision. Returns 'inserted' or 'updated'.

        Idempotent on (packet_id, dedupe_key): re-submitting the same form —
        which the offline-first page will do on every retry — must not multiply
        rows, and a changed answer must win.
        """
        existing = self.conn.execute(
            "SELECT id, decision, note FROM adjudications WHERE packet_id = ? AND dedupe_key = ?",
            (packet_id, dedupe_key)).fetchone()
        now = utcnow()
        with self.tx() as conn:
            if existing is None:
                conn.execute(
                    "INSERT INTO adjudications(packet_id, dedupe_key, section, decision,"
                    " note, decided_at, recorded_at, client_id, source)"
                    " VALUES(?,?,?,?,?,?,?,?,?)",
                    (packet_id, dedupe_key, section, decision, note, decided_at,
                     now, client_id, source))
                return "inserted"
            conn.execute(
                "UPDATE adjudications SET section=?, decision=?, note=?, decided_at=?,"
                " recorded_at=?, client_id=?, source=? WHERE id=?",
                (section, decision, note, decided_at, now, client_id, source,
                 existing["id"]))
            return "updated"

    def adjudications_for_packet(self, packet_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM adjudications WHERE packet_id = ? ORDER BY id",
            (packet_id,)).fetchall()

    def adjudicated_keys(self) -> set[str]:
        return {r["dedupe_key"] for r in self.conn.execute(
            "SELECT DISTINCT dedupe_key FROM adjudications").fetchall()}

    # --- tombstones -----------------------------------------------------------

    def add_tombstone(self, dedupe_key: str, centroid_text: str, reason: str) -> None:
        if not reason or not reason.strip():
            # A tombstone with no reason is a booby trap for whoever inherits it.
            raise ValueError("tombstone requires a reason")
        with self.tx() as conn:
            conn.execute(
                "INSERT INTO tombstones(dedupe_key, centroid_text, reason, created_at)"
                " VALUES(?,?,?,?) ON CONFLICT(dedupe_key) DO UPDATE SET"
                " centroid_text=excluded.centroid_text, reason=excluded.reason,"
                " cleared_at=NULL",
                (dedupe_key, centroid_text, reason.strip(), utcnow()))

    def active_tombstones(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM tombstones WHERE cleared_at IS NULL").fetchall()

    def bump_tombstone(self, tombstone_id: int) -> None:
        with self.tx() as conn:
            conn.execute(
                "UPDATE tombstones SET suppressed_count = suppressed_count + 1,"
                " last_suppressed_at = ? WHERE id = ?", (utcnow(), tombstone_id))

    # --- traffic --------------------------------------------------------------

    def record_traffic(self, records: Iterable[Any]) -> int:
        count = 0
        with self.tx() as conn:
            for rec in records:
                data = rec if isinstance(rec, dict) else rec.__dict__
                conn.execute(
                    "INSERT INTO cm_traffic(run_id, ts, method, path, params_json,"
                    " status, ok, duration_ms, bytes_in, rows, error)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (data.get("run_id"), data["ts"], data["method"], data["path"],
                     json.dumps(data.get("params") or {}), data.get("status"),
                     1 if data.get("ok") else 0, data.get("duration_ms", 0),
                     data.get("bytes_in", 0), data.get("rows"), data.get("error")))
                count += 1
        return count

    def traffic_summary(self, since_iso: str | None = None) -> dict:
        clause, params = "", []
        if since_iso:
            clause = " WHERE ts >= ?"
            params = [since_iso]
        row = self.conn.execute(
            "SELECT COUNT(*) requests, SUM(CASE WHEN ok=0 THEN 1 ELSE 0 END) failed,"
            " SUM(bytes_in) bytes_in, SUM(duration_ms) total_ms"
            f" FROM cm_traffic{clause}", params).fetchone()
        return {
            "requests": row["requests"] or 0,
            "failed": row["failed"] or 0,
            "bytes_in": row["bytes_in"] or 0,
            "total_ms": row["total_ms"] or 0,
        }
