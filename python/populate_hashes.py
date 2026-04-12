#!/usr/bin/env python3
"""
Populate file hashes for a completed scan.

Computes SHA-256 for all files in a scan, populates file_hashes table,
and identifies duplicate groups.

Usage:
    python populate_hashes.py --scan-id 33 --db /root/projects/DataArchive/data/archive.db
    python populate_hashes.py --scan-id 33 --db /root/projects/DataArchive/data/archive.db --batch-size 500
"""

import os
import sys
import argparse
import sqlite3
from pathlib import Path
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from utils.hash_utils import compute_sha256
from core.logger import get_logger

logger = get_logger(__name__)


class HashPopulator:

    def __init__(self, db_path: str, scan_id: int, batch_size: int = 1000):
        self.db_path = db_path
        self.scan_id = scan_id
        self.batch_size = batch_size
        self.conn = None

    def connect(self):
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def close(self):
        if self.conn:
            self.conn.close()

    def get_files_to_hash(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT f.file_id, f.path, f.size_bytes, s.mount_point
            FROM files f
            JOIN scans s ON f.scan_id = s.scan_id
            LEFT JOIN file_hashes fh ON f.file_id = fh.file_id AND fh.hash_type = 'sha256'
            WHERE f.scan_id = ? AND fh.hash_id IS NULL AND f.size_bytes > 0
            ORDER BY f.file_id
        ''', (self.scan_id,))
        return cursor.fetchall()

    def compute_and_store_hashes(self, files):
        cursor = self.conn.cursor()
        hash_batch = []
        processed = 0
        errors = 0
        now = datetime.now().isoformat()

        logger.info(f"Starting SHA-256 computation for {len(files):,} files")
        print(f"\nComputing SHA-256 for {len(files):,} files...")

        for i, file_row in enumerate(files, 1):
            file_id = file_row['file_id']
            relative_path = file_row['path']
            mount_point = file_row['mount_point'] or ''

            file_path = os.path.join(mount_point, relative_path)

            sha256_hash, error = compute_sha256(file_path)

            if error:
                errors += 1
                if errors <= 10:
                    logger.warning(f"Failed to hash {relative_path}: {error}")
                elif errors == 11:
                    logger.warning("Suppressing further individual error logs")
                continue

            hash_batch.append((self.scan_id, file_id, 'sha256', sha256_hash, now))
            processed += 1

            if len(hash_batch) >= self.batch_size:
                self._insert_hash_batch(cursor, hash_batch)
                self.conn.commit()
                hash_batch = []

                if processed % 10000 == 0:
                    pct = (i / len(files)) * 100
                    logger.info(f"Progress: {i:,}/{len(files):,} ({pct:.1f}%) - {errors} errors")
                    print(f"  {i:,}/{len(files):,} ({pct:.1f}%) - {processed:,} hashed, {errors} errors")

        if hash_batch:
            self._insert_hash_batch(cursor, hash_batch)
            self.conn.commit()

        logger.info(f"Hash computation complete: {processed:,} hashed, {errors} errors")
        print(f"\nCompleted: {processed:,} files hashed, {errors} errors")
        return processed, errors

    def _insert_hash_batch(self, cursor, hash_batch):
        cursor.executemany('''
            INSERT INTO file_hashes (scan_id, file_id, hash_type, hash_value, computed_at)
            VALUES (?, ?, ?, ?, ?)
        ''', hash_batch)

    def detect_duplicates(self):
        cursor = self.conn.cursor()
        print("\nDetecting duplicate groups...")

        cursor.execute('''
            SELECT hash_value, COUNT(*) as count
            FROM file_hashes
            WHERE scan_id = ? AND hash_type = 'sha256'
            GROUP BY hash_value
            HAVING COUNT(*) > 1
            ORDER BY count DESC
        ''', (self.scan_id,))

        dup_groups = cursor.fetchall()

        if not dup_groups:
            print("No within-scan duplicates found.")
            return 0

        print(f"Found {len(dup_groups):,} duplicate hash groups")
        return len(dup_groups)

    def generate_summary(self):
        cursor = self.conn.cursor()

        cursor.execute('SELECT COUNT(*) FROM file_hashes WHERE scan_id = ? AND hash_type = ?',
                        (self.scan_id, 'sha256'))
        total_hashed = cursor.fetchone()[0]

        cursor.execute('''
            SELECT hash_value, COUNT(*) as n
            FROM file_hashes
            WHERE scan_id = ? AND hash_type = 'sha256'
            GROUP BY hash_value
            HAVING COUNT(*) > 1
        ''', (self.scan_id,))
        dup_groups = cursor.fetchall()
        total_in_groups = sum(r['n'] for r in dup_groups)

        print(f"\n{'='*60}")
        print(f"SUMMARY")
        print(f"{'='*60}")
        print(f"Total files hashed (SHA-256): {total_hashed:,}")
        print(f"Duplicate groups: {len(dup_groups):,}")
        print(f"Files in duplicate groups: {total_in_groups:,}")
        print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description='Populate SHA-256 hashes for a scan')
    parser.add_argument('--scan-id', type=int, required=True, help='Scan ID to process')
    parser.add_argument('--db', default='data/archive.db', help='Database path')
    parser.add_argument('--batch-size', type=int, default=1000, help='Batch insert size')

    args = parser.parse_args()

    print(f"Populating SHA-256 hashes for scan {args.scan_id}")
    print(f"Database: {args.db}")

    populator = HashPopulator(args.db, args.scan_id, args.batch_size)

    try:
        populator.connect()
        files = populator.get_files_to_hash()

        if not files:
            print("No files need hashing (already processed or scan is empty)")
            return 0

        processed, errors = populator.compute_and_store_hashes(files)

        if processed == 0:
            print("No hashes computed")
            return 1

        populator.detect_duplicates()
        populator.generate_summary()
        return 0

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        print(f"\nError: {e}")
        return 1

    finally:
        populator.close()


if __name__ == '__main__':
    sys.exit(main())
