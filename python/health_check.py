#!/usr/bin/env python3
"""
Drive health check — read-based assessment from WSL.

Tests drive readability by walking the entire filesystem tree and
performing timed sample reads on a random subset of files.  Results
are stored in the drive_health_checks table.

If a matching SMART JSON file exists in Harvester/smart/<drive_code>-smart.json,
it is also ingested as a second row with check_type='smart'.

Usage:
    python3 health_check.py /mnt/h --drive-code POCL --db /root/projects/DataArchive/data/archive.db
    python3 health_check.py /mnt/h --drive-code POCL --sample-count 1000
"""

import argparse
import json
import os
import random
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Logging — use the project logger when available, fall back to stdlib
# ---------------------------------------------------------------------------
try:
    # Add parent dir to path so `core` package resolves when invoked from
    # the python/ directory or from the repo root.
    _script_dir = Path(__file__).resolve().parent
    if str(_script_dir) not in sys.path:
        sys.path.insert(0, str(_script_dir))
    from core.logger import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s - %(levelname)s - %(message)s")
    logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Migration bootstrap — ensure the table exists
# ---------------------------------------------------------------------------

def _ensure_table(conn: sqlite3.Connection, migrations_dir: Path) -> None:
    """Run migration 003 if the table doesn't exist yet."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='drive_health_checks'"
    )
    if cursor.fetchone():
        return  # table already present

    migration_file = migrations_dir / "003_add_drive_health_checks.sql"
    if not migration_file.exists():
        logger.error(
            "drive_health_checks table does not exist and migration file "
            f"not found at {migration_file}.  Run apply_migrations.py first."
        )
        sys.exit(1)

    logger.info("drive_health_checks table missing — applying migration 003")
    with open(migration_file, "r", encoding="utf-8") as f:
        sql = f.read()
    try:
        conn.executescript(sql)
        conn.commit()
        logger.info("Migration 003 applied successfully")
    except sqlite3.OperationalError as exc:
        # schema_migrations INSERT may fail if already recorded (idempotent)
        if "unique constraint" in str(exc).lower() or "already" in str(exc).lower():
            conn.commit()
        else:
            raise


# ---------------------------------------------------------------------------
# Resolve drive_id from drive_code
# ---------------------------------------------------------------------------

def _resolve_drive_id(conn: sqlite3.Connection, drive_code: str):
    """Return drive_id for a drive_code, or None."""
    cursor = conn.execute(
        "SELECT drive_id FROM drives WHERE drive_code = ? ORDER BY last_scanned DESC LIMIT 1",
        (drive_code,),
    )
    row = cursor.fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Phase 1 — directory walk
# ---------------------------------------------------------------------------

def walk_filesystem(mount_point: str):
    """Walk the entire mount point.  Returns (file_paths, unreadable_paths, walk_secs)."""
    file_paths: list[str] = []
    unreadable_paths: list[dict] = []
    t0 = time.monotonic()

    for dirpath, _dirnames, filenames in os.walk(mount_point):
        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            try:
                # Just stat — confirms the path is reachable
                os.stat(fpath)
                file_paths.append(fpath)
            except (OSError, PermissionError) as exc:
                unreadable_paths.append({"path": fpath, "error": str(exc)})

    walk_secs = time.monotonic() - t0
    return file_paths, unreadable_paths, walk_secs


# ---------------------------------------------------------------------------
# Phase 2 — sample file reads
# ---------------------------------------------------------------------------

def sample_read_test(file_paths: list[str], sample_count: int):
    """Read a random sample of files fully.  Returns (results, errors, total_bytes, total_secs)."""
    if not file_paths:
        return [], [], 0, 0.0

    sample_size = min(sample_count, len(file_paths))
    sample = random.sample(file_paths, sample_size)

    results: list[dict] = []
    errors: list[dict] = []
    total_bytes = 0
    total_secs = 0.0

    for fpath in sample:
        t0 = time.monotonic()
        try:
            with open(fpath, "rb") as fh:
                data = fh.read()
            elapsed = time.monotonic() - t0
            nbytes = len(data)
            total_bytes += nbytes
            total_secs += elapsed
            speed_mbps = (nbytes / (1024 * 1024)) / elapsed if elapsed > 0 else 0.0
            results.append({
                "path": fpath,
                "bytes": nbytes,
                "secs": round(elapsed, 4),
                "mbps": round(speed_mbps, 2),
            })
        except (OSError, PermissionError) as exc:
            elapsed = time.monotonic() - t0
            total_secs += elapsed
            errors.append({"path": fpath, "error": str(exc), "secs": round(elapsed, 4)})

    return results, errors, total_bytes, total_secs


# ---------------------------------------------------------------------------
# Status classification
# ---------------------------------------------------------------------------

def classify_status(
    total_files: int,
    unreadable_count: int,
    sample_count: int,
    read_error_count: int,
) -> str:
    """Return 'healthy', 'degraded', or 'failing'."""
    if total_files == 0:
        return "healthy"

    unreadable_pct = (unreadable_count / total_files) * 100
    error_pct = (read_error_count / sample_count) * 100 if sample_count > 0 else 0

    if error_pct > 5 or unreadable_pct > 10:
        return "failing"
    if read_error_count > 0 or unreadable_pct > 1:
        return "degraded"
    return "healthy"


# ---------------------------------------------------------------------------
# Store read-test results
# ---------------------------------------------------------------------------

def store_read_test(
    conn: sqlite3.Connection,
    *,
    drive_id,
    drive_code: str,
    mount_point: str,
    disk_usage,
    files_walked: int,
    unreadable_files: int,
    unreadable_paths: list[dict],
    read_errors: int,
    read_error_details: list[dict],
    sample_count: int,
    sample_bytes: int,
    sample_duration_secs: float,
    avg_read_speed_mbps: float,
    walk_duration_secs: float,
    overall_status: str,
    sample_results: list[dict],
):
    details = {
        "unreadable_paths": unreadable_paths,
        "read_errors": read_error_details,
        "sample_timings": sample_results,
    }

    conn.execute(
        """
        INSERT INTO drive_health_checks (
            drive_id, drive_code, check_date, mount_point, check_type,
            total_bytes, used_bytes, free_bytes,
            files_walked, unreadable_files, read_errors,
            sample_count, sample_bytes, sample_duration_secs,
            avg_read_speed_mbps, walk_duration_secs,
            overall_status, details_json
        ) VALUES (?, ?, ?, ?, 'read_test',
                  ?, ?, ?,
                  ?, ?, ?,
                  ?, ?, ?,
                  ?, ?,
                  ?, ?)
        """,
        (
            drive_id,
            drive_code,
            datetime.now(timezone.utc).isoformat(),
            mount_point,
            disk_usage.total,
            disk_usage.used,
            disk_usage.free,
            files_walked,
            unreadable_files,
            read_errors,
            sample_count,
            sample_bytes,
            round(sample_duration_secs, 3),
            round(avg_read_speed_mbps, 3),
            round(walk_duration_secs, 3),
            overall_status,
            json.dumps(details),
        ),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# SMART JSON ingestion
# ---------------------------------------------------------------------------

def ingest_smart_json(conn: sqlite3.Connection, drive_code: str, drive_id, smart_path: Path):
    """Read a SMART JSON file and insert a check_type='smart' row."""
    logger.info(f"Found SMART data: {smart_path}")
    with open(smart_path, "r", encoding="utf-8") as f:
        smart_data = json.load(f)

    # Derive an overall status from the Windows HealthStatus field
    health = smart_data.get("health_status", "").lower()
    if health in ("healthy", "ok", "0"):
        overall = "healthy"
    elif health in ("warning", "degraded", "1"):
        overall = "degraded"
    else:
        overall = "failing" if health else "healthy"

    conn.execute(
        """
        INSERT INTO drive_health_checks (
            drive_id, drive_code, check_date, mount_point, check_type,
            overall_status, details_json
        ) VALUES (?, ?, ?, NULL, 'smart', ?, ?)
        """,
        (
            drive_id,
            drive_code,
            smart_data.get("timestamp", datetime.now(timezone.utc).isoformat()),
            overall,
            json.dumps(smart_data),
        ),
    )
    conn.commit()
    logger.info(f"SMART data ingested (status: {overall})")


# ---------------------------------------------------------------------------
# Human-readable summary
# ---------------------------------------------------------------------------

def print_summary(
    mount_point: str,
    drive_code: str,
    disk_usage,
    files_walked: int,
    unreadable_count: int,
    walk_secs: float,
    sample_count: int,
    sample_bytes: int,
    sample_secs: float,
    avg_speed: float,
    read_errors: int,
    overall_status: str,
    smart_ingested: bool,
):
    gb = 1024 ** 3
    print()
    print("=" * 60)
    print(f"  DRIVE HEALTH CHECK — {drive_code} ({mount_point})")
    print("=" * 60)
    print()
    print(f"  Disk space:      {disk_usage.total / gb:>8.2f} GB total")
    print(f"                   {disk_usage.used / gb:>8.2f} GB used")
    print(f"                   {disk_usage.free / gb:>8.2f} GB free")
    print()
    print(f"  Directory walk:  {files_walked:>8,} files found")
    print(f"                   {unreadable_count:>8,} unreadable")
    print(f"                   {walk_secs:>8.1f} seconds")
    print()
    print(f"  Sample reads:    {sample_count:>8,} files read")
    print(f"                   {sample_bytes / gb:>8.2f} GB read")
    print(f"                   {sample_secs:>8.1f} seconds")
    print(f"                   {avg_speed:>8.1f} MB/s avg")
    print(f"                   {read_errors:>8,} errors")
    print()

    status_display = {
        "healthy": "HEALTHY",
        "degraded": "DEGRADED",
        "failing": "FAILING",
    }
    print(f"  Overall status:  {status_display.get(overall_status, overall_status)}")
    if smart_ingested:
        print(f"  SMART data:      ingested from Harvester/smart/")
    print()
    print("=" * 60)
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Drive health check — read-based assessment from WSL"
    )
    parser.add_argument(
        "mount_point",
        help="Mount point to check (e.g., /mnt/h)",
    )
    parser.add_argument(
        "--drive-code",
        required=True,
        help="Short drive code tag (e.g., POCL)",
    )
    parser.add_argument(
        "--db",
        default="/root/projects/DataArchive/data/archive.db",
        help="Path to archive.db (default: /root/projects/DataArchive/data/archive.db)",
    )
    parser.add_argument(
        "--sample-count",
        type=int,
        default=500,
        help="Number of files to sample-read (default: 500)",
    )
    args = parser.parse_args()

    mount_point = args.mount_point
    drive_code = args.drive_code
    db_path = Path(args.db)
    sample_target = args.sample_count

    # Validate mount point
    if not os.path.isdir(mount_point):
        logger.error(f"Mount point does not exist or is not a directory: {mount_point}")
        return 1

    # Resolve project root for migration + SMART file paths
    project_root = Path(__file__).resolve().parent.parent
    migrations_dir = project_root / "migrations"
    smart_dir = project_root / "Harvester" / "smart"

    # Open database
    if not db_path.exists():
        logger.error(f"Database not found: {db_path}")
        return 1

    conn = sqlite3.connect(str(db_path), timeout=30.0)
    try:
        _ensure_table(conn, migrations_dir)
        drive_id = _resolve_drive_id(conn, drive_code)

        if drive_id:
            logger.info(f"Resolved drive_code={drive_code} to drive_id={drive_id}")
        else:
            logger.warning(
                f"No drive record found for drive_code={drive_code}; "
                "health check will store drive_id=NULL"
            )

        # ── Phase 0: disk usage ──────────────────────────────────────
        logger.info(f"Checking disk usage for {mount_point}")
        disk_usage = shutil.disk_usage(mount_point)
        logger.info(
            f"Disk: {disk_usage.total / (1024**3):.2f} GB total, "
            f"{disk_usage.used / (1024**3):.2f} GB used, "
            f"{disk_usage.free / (1024**3):.2f} GB free"
        )

        # ── Phase 1: full directory walk ─────────────────────────────
        logger.info(f"Walking filesystem at {mount_point} ...")
        file_paths, unreadable_paths, walk_secs = walk_filesystem(mount_point)
        files_walked = len(file_paths)
        unreadable_count = len(unreadable_paths)
        logger.info(
            f"Walk complete: {files_walked:,} files, "
            f"{unreadable_count:,} unreadable, "
            f"{walk_secs:.1f}s"
        )

        # ── Phase 2: sample read test ────────────────────────────────
        logger.info(f"Reading sample of {min(sample_target, files_walked)} files ...")
        sample_results, read_error_details, sample_bytes, sample_secs = sample_read_test(
            file_paths, sample_target
        )
        actual_sample = len(sample_results) + len(read_error_details)
        read_errors = len(read_error_details)
        avg_speed = (sample_bytes / (1024 * 1024)) / sample_secs if sample_secs > 0 else 0.0
        logger.info(
            f"Sample complete: {actual_sample} files, "
            f"{sample_bytes / (1024**2):.1f} MB, "
            f"{avg_speed:.1f} MB/s, "
            f"{read_errors} errors"
        )

        # ── Phase 3: classify ────────────────────────────────────────
        overall_status = classify_status(
            files_walked, unreadable_count, actual_sample, read_errors
        )
        logger.info(f"Overall status: {overall_status}")

        # ── Phase 4: store read-test results ─────────────────────────
        store_read_test(
            conn,
            drive_id=drive_id,
            drive_code=drive_code,
            mount_point=mount_point,
            disk_usage=disk_usage,
            files_walked=files_walked,
            unreadable_files=unreadable_count,
            unreadable_paths=unreadable_paths,
            read_errors=read_errors,
            read_error_details=read_error_details,
            sample_count=actual_sample,
            sample_bytes=sample_bytes,
            sample_duration_secs=sample_secs,
            avg_read_speed_mbps=avg_speed,
            walk_duration_secs=walk_secs,
            overall_status=overall_status,
            sample_results=sample_results,
        )
        logger.info("Read-test results stored in drive_health_checks")

        # ── Phase 5: ingest SMART data if available ──────────────────
        smart_file = smart_dir / f"{drive_code}-smart.json"
        smart_ingested = False
        if smart_file.exists():
            try:
                ingest_smart_json(conn, drive_code, drive_id, smart_file)
                smart_ingested = True
            except Exception as exc:
                logger.error(f"Failed to ingest SMART data: {exc}", exc_info=True)
        else:
            logger.info(
                f"No SMART data found at {smart_file} — "
                "run collect-smart.ps1 from Windows to collect it"
            )

        # ── Summary ──────────────────────────────────────────────────
        print_summary(
            mount_point=mount_point,
            drive_code=drive_code,
            disk_usage=disk_usage,
            files_walked=files_walked,
            unreadable_count=unreadable_count,
            walk_secs=walk_secs,
            sample_count=actual_sample,
            sample_bytes=sample_bytes,
            sample_secs=sample_secs,
            avg_speed=avg_speed,
            read_errors=read_errors,
            overall_status=overall_status,
            smart_ingested=smart_ingested,
        )

        return 0

    except Exception as exc:
        logger.error(f"Health check failed: {exc}", exc_info=True)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
