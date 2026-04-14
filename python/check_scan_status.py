#!/usr/bin/env python3
"""Quick script to check scan status in database"""
import sqlite3
from pathlib import Path

db_path = Path(__file__).parent / "output" / "archive.db"

if not db_path.exists():
    print(f"Database not found: {db_path}")
    exit(1)

conn = sqlite3.connect(str(db_path))
conn.row_factory = sqlite3.Row

# Check scans
print("=" * 80)
print("RECENT SCANS")
print("=" * 80)
cursor = conn.execute("""
    SELECT scan_id, drive_id, file_count, total_size_bytes, status,
           scan_start, scan_end, mount_point
    FROM scans
    ORDER BY scan_id DESC
    LIMIT 5
""")
for row in cursor:
    size_gb = f"{row['total_size_bytes']/(1024**3):.2f}" if row['total_size_bytes'] else "0.00"
    print(f"Scan ID: {row['scan_id']}")
    print(f"  Drive: {row['drive_id']} | Mount: {row['mount_point']}")
    print(f"  Files: {row['file_count'] or 0:,} | Size: {size_gb} GB")
    print(f"  Status: {row['status'] or 'NULL'}")
    print(f"  Started: {row['scan_start']}")
    print(f"  Ended: {row['scan_end'] or 'Not finished'}")
    print()

# Check file counts per scan
print("=" * 80)
print("FILE COUNTS BY SCAN")
print("=" * 80)
cursor = conn.execute("""
    SELECT scan_id, COUNT(*) as actual_files,
           COUNT(CASE WHEN sha256_hash IS NOT NULL THEN 1 END) as hashed_files
    FROM files
    GROUP BY scan_id
    ORDER BY scan_id DESC
""")
for row in cursor:
    print(f"Scan {row['scan_id']}: {row['actual_files']:,} files total, {row['hashed_files']:,} with SHA-256")

conn.close()
