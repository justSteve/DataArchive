#!/usr/bin/env python3
"""
Resume an incomplete scan by adding files that exist on the drive but aren't in the database.
"""

import sys
import os
import sqlite3
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent / 'python'))
from core.logger import get_logger

logger = get_logger(__name__)


def get_existing_files(scan_id, db_path):
    """Get set of file paths already in the database for this scan"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute('SELECT path FROM files WHERE scan_id = ?', (scan_id,))
    existing = {row[0] for row in cursor.fetchall()}

    conn.close()
    return existing


def enumerate_drive(drive_path):
    """Enumerate all files on a drive, returning relative paths"""
    logger.info(f"Enumerating files on {drive_path}...")

    files = []
    drive_root = Path(drive_path)

    for root, dirs, filenames in os.walk(drive_path):
        for filename in filenames:
            full_path = Path(root) / filename

            try:
                # Get relative path from drive root
                relative_path = full_path.relative_to(drive_root)

                # Get file stats
                stat = full_path.stat()

                files.append({
                    'path': str(relative_path).replace('/', '\\'),  # Windows-style paths
                    'size_bytes': stat.st_size,
                    'modified_date': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    'created_date': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    'accessed_date': datetime.fromtimestamp(stat.st_atime).isoformat(),
                    'extension': full_path.suffix.lower() if full_path.suffix else '',
                    'is_hidden': bool(stat.st_file_attributes & 0x2) if hasattr(stat, 'st_file_attributes') else False,
                    'is_system': bool(stat.st_file_attributes & 0x4) if hasattr(stat, 'st_file_attributes') else False
                })

                if len(files) % 10000 == 0:
                    print(f"  Enumerated {len(files):,} files...")

            except (PermissionError, OSError) as e:
                logger.warning(f"Cannot access {full_path}: {e}")
                continue

    logger.info(f"Enumeration complete: {len(files):,} files found")
    return files


def find_missing_files(all_files, existing_paths):
    """Find files that aren't in the database"""
    missing = []

    for file_info in all_files:
        if file_info['path'] not in existing_paths:
            missing.append(file_info)

    return missing


def add_files_to_scan(scan_id, files, db_path, batch_size=1000):
    """Add missing files to an existing scan"""
    if not files:
        print("No missing files to add")
        return 0

    print(f"\nAdding {len(files):,} missing files to scan {scan_id}...")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    added = 0
    batch = []

    for i, file_info in enumerate(files, 1):
        batch.append({
            'scan_id': scan_id,
            'path': file_info['path'],
            'size_bytes': file_info['size_bytes'],
            'modified_date': file_info['modified_date'],
            'created_date': file_info['created_date'],
            'accessed_date': file_info['accessed_date'],
            'extension': file_info['extension'],
            'is_hidden': file_info['is_hidden'],
            'is_system': file_info['is_system']
        })

        if len(batch) >= batch_size:
            cursor.executemany('''
                INSERT INTO files (scan_id, path, size_bytes, modified_date, created_date, accessed_date, extension, is_hidden, is_system)
                VALUES (:scan_id, :path, :size_bytes, :modified_date, :created_date, :accessed_date, :extension, :is_hidden, :is_system)
            ''', batch)
            conn.commit()
            added += len(batch)
            batch = []

            pct = (i / len(files)) * 100
            print(f"  Progress: {i:,}/{len(files):,} ({pct:.1f}%)")

    # Insert remaining
    if batch:
        cursor.executemany('''
            INSERT INTO files (scan_id, path, size_bytes, modified_date, created_date, accessed_date, extension, is_hidden, is_system)
            VALUES (:scan_id, :path, :size_bytes, :modified_date, :created_date, :accessed_date, :extension, :is_hidden, :is_system)
        ''', batch)
        conn.commit()
        added += len(batch)

    conn.close()
    print(f"\nAdded {added:,} files to scan {scan_id}")
    return added


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Resume incomplete scan')
    parser.add_argument('drive_path', help='Drive path (e.g., Z:\\)')
    parser.add_argument('--scan-id', type=int, required=True, help='Scan ID to resume')
    parser.add_argument('--db', default='output/archive.db', help='Database path')
    parser.add_argument('--batch-size', type=int, default=1000, help='Batch insert size')

    args = parser.parse_args()

    print(f"Resuming scan {args.scan_id} for {args.drive_path}")

    # Get existing files from database
    existing_paths = get_existing_files(args.scan_id, args.db)
    print(f"Database has {len(existing_paths):,} files for scan {args.scan_id}")

    # Enumerate all files on drive
    all_files = enumerate_drive(args.drive_path)
    print(f"Drive has {len(all_files):,} files currently")

    # Find missing files
    missing_files = find_missing_files(all_files, existing_paths)
    print(f"Found {len(missing_files):,} files missing from database")

    if missing_files:
        # Add missing files to scan
        added = add_files_to_scan(args.scan_id, missing_files, args.db, args.batch_size)
        print(f"\nScan {args.scan_id} now has {len(existing_paths) + added:,} total files")
    else:
        print("\nScan is complete - no missing files")
