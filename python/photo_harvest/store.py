"""photo_harvest table access. [co-06tcu]

The table is created by migrations/004_add_photo_harvest.sql. Every write
stamps updated_at; nothing here deletes a row.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

STATUSES = (
    "pending", "skipped_small", "skipped_path", "unreadable", "held_sensitive", "ready",
    "submitted", "described", "declined", "failed",
)


class StoreError(RuntimeError):
    pass


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 60000")
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='photo_harvest'"
    ).fetchone()
    if row is None:
        raise StoreError(
            f"{db_path} has no photo_harvest table; run apply_migrations.py first"
        )
    return conn


def update(conn: sqlite3.Connection, sha256: str, **fields) -> None:
    if "status" in fields and fields["status"] not in STATUSES:
        raise StoreError(f"unknown status {fields['status']!r}")
    cols = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(
        f"UPDATE photo_harvest SET {cols}, updated_at = datetime('now') WHERE sha256 = ?",
        (*fields.values(), sha256),
    )


def by_status(conn: sqlite3.Connection, status: str, limit: int | None = None):
    sql = "SELECT * FROM photo_harvest WHERE status = ? ORDER BY sha256"
    args: tuple = (status,)
    if limit:
        sql += " LIMIT ?"
        args += (limit,)
    return conn.execute(sql, args).fetchall()


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    return dict(conn.execute(
        "SELECT status, COUNT(*) FROM photo_harvest GROUP BY status"
    ).fetchall())
