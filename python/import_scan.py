#!/usr/bin/env python3
"""
Import JSONL scan results (from scan_drive_win.py) into archive.db

Reads a JSONL file produced by the Windows-native scanner and inserts the
drive, scan, file, and hash records into the DataArchive SQLite database.

Usage:
    python3 import_scan.py scan-POCL-20260504.jsonl
    python3 import_scan.py scan-POCL-20260504.jsonl --db data/archive.db
    python3 import_scan.py scan-POCL-20260504.jsonl --dry-run

JSONL format expected:
    Line 1:  {"type": "drive", "serial_number": "...", "model": "...", ...}
    Lines:   {"type": "file",  "path": "...", "size_bytes": ..., ...}
    Last:    {"type": "summary", "total_files": ..., ...}
"""

import sys
import json
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime

# Add project root so core/ is importable
sys.path.insert(0, str(Path(__file__).parent))

from core.database import Database


def read_jsonl(filepath: str):
    """
    Parse a JSONL file, yielding one dict per line.
    Skips blank lines; raises on malformed JSON.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                print(f"WARNING: malformed JSON on line {lineno}: {e}", file=sys.stderr)


def import_drive(db: Database, drive_rec: dict) -> int:
    """
    Insert or update the drive record.  Returns drive_id.
    """
    drive_info = {
        "serial_number": drive_rec["serial_number"],
        "model": drive_rec.get("model"),
        "manufacturer": drive_rec.get("manufacturer"),
        "size_bytes": drive_rec.get("size_bytes"),
        "filesystem": drive_rec.get("filesystem"),
        "partition_scheme": None,
        "label": drive_rec.get("drive_label") or drive_rec.get("volume_label"),
        "connection_type": drive_rec.get("connection_method"),
        "firmware_version": drive_rec.get("firmware_version"),
        "media_type": drive_rec.get("media_type"),
        "bus_type": drive_rec.get("bus_type"),
        "notes": None,
        "drive_code": drive_rec.get("drive_code"),
    }
    return db.insert_drive(drive_info)


def main():
    parser = argparse.ArgumentParser(
        description="Import JSONL scan results into archive.db"
    )
    parser.add_argument(
        "jsonl_file",
        help="Path to JSONL file produced by scan_drive_win.py",
    )
    parser.add_argument(
        "--db",
        default="data/archive.db",
        help="Path to SQLite database (default: data/archive.db)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate JSONL without writing to DB",
    )

    args = parser.parse_args()

    jsonl_path = args.jsonl_file
    if not Path(jsonl_path).exists():
        print(f"ERROR: {jsonl_path} not found", file=sys.stderr)
        return 1

    # ---------------------------------------------------------------
    # Pass 1: read and categorize records
    # ---------------------------------------------------------------
    drive_rec = None
    file_recs = []
    summary_rec = None

    for rec in read_jsonl(jsonl_path):
        rtype = rec.get("type")
        if rtype == "drive":
            drive_rec = rec
        elif rtype == "file":
            file_recs.append(rec)
        elif rtype == "summary":
            summary_rec = rec
        else:
            print(f"WARNING: unknown record type '{rtype}', skipping", file=sys.stderr)

    if drive_rec is None:
        print("ERROR: no drive record found in JSONL", file=sys.stderr)
        return 1

    # Report what we found
    print(f"JSONL: {jsonl_path}")
    print(f"  Drive:  {drive_rec.get('model', '?')} (S/N: {drive_rec.get('serial_number', '?')})")
    print(f"  Code:   {drive_rec.get('drive_code', '(none)')}")
    print(f"  Files:  {len(file_recs):,}")
    if summary_rec:
        print(f"  Summary: {summary_rec.get('total_files', '?')} files, "
              f"{summary_rec.get('errors', '?')} errors, "
              f"{summary_rec.get('scan_duration_secs', '?')}s")

    hashed_count = sum(1 for f in file_recs if f.get("hash"))
    if hashed_count:
        print(f"  Hashes: {hashed_count:,} files have SHA-256")

    if args.dry_run:
        print("\n[DRY RUN] No changes written to database.")
        return 0

    # ---------------------------------------------------------------
    # Pass 2: write to database
    # ---------------------------------------------------------------
    print(f"\nDatabase: {args.db}")
    db = Database(args.db)

    # 1. Drive record
    drive_id = import_drive(db, drive_rec)
    print(f"  Drive ID: {drive_id}")

    # 2. Start scan session
    mount_point = drive_rec.get("scan_source", "Windows")
    scan_id = db.start_scan(drive_id, mount_point)
    print(f"  Scan ID:  {scan_id}")

    # 3. Batch-insert file records
    batch = []
    batch_size = 1000
    total_files = 0
    total_size = 0
    hash_batch = []  # collect (index_in_batch_offset, hash_value) for later

    # We need file_ids for hash records.  Strategy: insert files in batches,
    # then query back the file_ids by (scan_id, path) for hashed files.
    # More efficient: note that insert_files_batch doesn't return IDs, so
    # we'll do a second pass for hashes using raw SQL.

    hashed_paths = {}  # path -> hash_value  (collect during insert)

    for rec in file_recs:
        file_entry = {
            "path": rec["path"],
            "size_bytes": rec.get("size_bytes", 0),
            "modified_date": rec.get("modified_date"),
            "created_date": rec.get("created_date"),
            "accessed_date": None,
            "extension": rec.get("extension", ""),
            "is_hidden": rec.get("is_hidden", False),
            "is_system": rec.get("is_system", False),
            "priority": "medium",
        }
        batch.append(file_entry)
        total_files += 1
        total_size += rec.get("size_bytes", 0)

        if rec.get("hash"):
            hashed_paths[rec["path"]] = rec["hash"]

        if len(batch) >= batch_size:
            db.insert_files_batch(scan_id, batch)
            batch = []
            if total_files % 50000 == 0:
                print(f"  {total_files:,} files imported...")

    # Remaining batch
    if batch:
        db.insert_files_batch(scan_id, batch)

    print(f"  Imported {total_files:,} files ({total_size / (1024**3):.2f} GB)")

    # 4. Insert hash records
    if hashed_paths:
        print(f"  Linking {len(hashed_paths):,} hash records...")
        _insert_hashes(db, scan_id, hashed_paths)
        print(f"  Hash records inserted")

    # 5. Complete scan
    db.complete_scan(scan_id, total_files, total_size)

    # 6. Summary
    print()
    print("=" * 60)
    print("IMPORT COMPLETE")
    print("=" * 60)
    print(f"  Drive:  {drive_rec.get('model')} [{drive_rec.get('drive_code', '')}]")
    print(f"  Scan:   {scan_id}")
    print(f"  Files:  {total_files:,}")
    print(f"  Size:   {total_size / (1024**3):.2f} GB")
    if hashed_paths:
        print(f"  Hashes: {len(hashed_paths):,} SHA-256 records")
    print("=" * 60)

    return 0


def _insert_hashes(db: Database, scan_id: int, hashed_paths: dict):
    """
    Look up file_ids for hashed paths and insert into file_hashes.

    hashed_paths: {relative_path: "sha256:<hex>"}
    """
    # Batch query file_ids.  For very large sets, chunk the query.
    batch_size = 500
    paths_list = list(hashed_paths.keys())
    hash_records = []

    for i in range(0, len(paths_list), batch_size):
        chunk = paths_list[i:i + batch_size]
        placeholders = ",".join("?" for _ in chunk)

        with db.get_connection("lookup_file_ids") as conn:
            cursor = conn.execute(
                f"SELECT file_id, path FROM files "
                f"WHERE scan_id = ? AND path IN ({placeholders})",
                [scan_id] + chunk,
            )
            for row in cursor:
                file_id = row["file_id"]
                path = row["path"]
                raw_hash = hashed_paths[path]
                # Strip "sha256:" prefix for storage
                hash_value = raw_hash.split(":", 1)[1] if ":" in raw_hash else raw_hash
                hash_records.append({
                    "scan_id": scan_id,
                    "file_id": file_id,
                    "hash_type": "sha256",
                    "hash_value": hash_value,
                })

        # Flush hash records in batches
        if len(hash_records) >= 1000:
            db.insert_file_hashes_batch(hash_records)
            hash_records = []

    # Remaining
    if hash_records:
        db.insert_file_hashes_batch(hash_records)


if __name__ == "__main__":
    sys.exit(main())
