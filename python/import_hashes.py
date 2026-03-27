#!/usr/bin/env python3
"""
Import hash CSV from Windows-native hash-drive.ps1 into archive.db

Matches files by path against existing file records, writes to file_hashes table.
Supports cross-drive dedup: same SHA256 = same content regardless of source drive.

Usage:
    python import_hashes.py D --label WWYY
    python import_hashes.py E --label Tera1A
"""

import sys
import csv
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime


def main():
    parser = argparse.ArgumentParser(description='Import file hashes into archive.db')
    parser.add_argument('drive_letter', help='Drive letter that was hashed (e.g., D)')
    parser.add_argument('--label', required=True, help='Drive label (e.g., WWYY)')
    parser.add_argument('--db', default='output/archive.db', help='Database path')
    parser.add_argument('--hash-dir', default='/mnt/c/DataArchive', help='Where hash-X.csv lives')
    args = parser.parse_args()

    dl = args.drive_letter.strip(':').upper()
    hash_dir = Path(args.hash_dir)
    csv_file = hash_dir / f'hash-{dl}.csv'

    if not csv_file.exists():
        print(f"ERROR: {csv_file} not found")
        sys.exit(1)

    db = sqlite3.connect(args.db)
    db.execute("PRAGMA journal_mode=WAL")

    # Find the scan_id for this drive label
    row = db.execute("""
        SELECT s.scan_id FROM scans s
        JOIN drives d ON s.drive_id = d.drive_id
        WHERE d.label = ? OR d.drive_code = ?
        ORDER BY s.scan_id DESC LIMIT 1
    """, (args.label, args.label)).fetchone()

    if not row:
        print(f"ERROR: No scan found for drive label '{args.label}'")
        sys.exit(1)

    scan_id = row[0]
    print(f"Importing hashes for {args.label} (scan_id={scan_id}) from {csv_file}")

    # Build a lookup of path -> file_id from existing file records
    # Normalize: DB stores paths like D:\folder\file.txt
    print("Building file path index...")
    path_to_id = {}
    for file_id, path in db.execute("SELECT file_id, path FROM files WHERE scan_id = ?", (scan_id,)):
        path_to_id[path.replace('\\', '/').upper()] = file_id
    print(f"  {len(path_to_id)} files in database for this scan")

    # Check for existing hashes to avoid duplicates
    existing = set()
    for (fid,) in db.execute("SELECT file_id FROM file_hashes WHERE scan_id = ?", (scan_id,)):
        existing.add(fid)
    if existing:
        print(f"  {len(existing)} files already hashed, will skip those")

    now = datetime.now().isoformat()
    imported = 0
    matched = 0
    unmatched = 0
    skipped = 0
    batch = []

    with open(csv_file, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        header = next(reader)  # skip header

        for row in reader:
            if len(row) < 3:
                continue
            file_path, size_str, sha256 = row[0], row[1], row[2]

            # Strip drive letter prefix (e.g., "D:\") and normalize separators to match DB
            rel_path = file_path
            if len(rel_path) >= 3 and rel_path[1] == ':' and rel_path[2] == '\\':
                rel_path = rel_path[3:]
            rel_path = rel_path.replace('\\', '/')

            file_id = path_to_id.get(rel_path.upper())
            if file_id is None:
                unmatched += 1
                continue

            matched += 1

            if file_id in existing:
                skipped += 1
                continue

            batch.append((scan_id, file_id, 'sha256', sha256, now))

            if len(batch) >= 5000:
                db.executemany(
                    "INSERT INTO file_hashes (scan_id, file_id, hash_type, hash_value, computed_at) VALUES (?,?,?,?,?)",
                    batch
                )
                db.commit()
                imported += len(batch)
                print(f"  {imported} hashes imported, {matched} matched, {unmatched} unmatched...")
                batch = []

    if batch:
        db.executemany(
            "INSERT INTO file_hashes (scan_id, file_id, hash_type, hash_value, computed_at) VALUES (?,?,?,?,?)",
            batch
        )
        db.commit()
        imported += len(batch)

    db.close()

    print(f"\nDone:")
    print(f"  Matched to DB records: {matched}")
    print(f"  New hashes imported:   {imported}")
    print(f"  Already hashed:        {skipped}")
    print(f"  No DB match (skipped): {unmatched}")


if __name__ == '__main__':
    main()
