#!/usr/bin/env python3
"""
Populate file hashes for a completed scan.

Computes quick_hash (and optionally SHA-256) for all files in a scan,
populates file_hashes table, and identifies duplicate groups.

Usage:
    python populate_hashes.py --scan-id 3 [--verify-sha256] [--batch-size 1000]
"""

import sys
import argparse
import sqlite3
from pathlib import Path
from collections import defaultdict
from datetime import datetime

# Add python directory to path
sys.path.insert(0, str(Path(__file__).parent / 'python'))

from utils.hash_utils import compute_quick_hash, compute_sha256
from core.logger import get_logger

logger = get_logger(__name__)


class HashPopulator:
    """Populates file hashes for a scan and detects duplicates"""

    def __init__(self, db_path: str, scan_id: int, verify_sha256: bool = False, batch_size: int = 1000):
        self.db_path = db_path
        self.scan_id = scan_id
        self.verify_sha256 = verify_sha256
        self.batch_size = batch_size
        self.conn = None

    def connect(self):
        """Connect to database"""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()

    def get_files_to_hash(self):
        """Get all files from scan that need hashing"""
        cursor = self.conn.cursor()

        # Get files not yet in file_hashes table, with mount_point
        cursor.execute('''
            SELECT f.file_id, f.path, f.size_bytes, s.mount_point
            FROM files f
            JOIN scans s ON f.scan_id = s.scan_id
            LEFT JOIN file_hashes fh ON f.file_id = fh.file_id
            WHERE f.scan_id = ? AND fh.hash_id IS NULL
            ORDER BY f.file_id
        ''', (self.scan_id,))

        return cursor.fetchall()

    def compute_and_store_hashes(self, files):
        """Compute hashes for files and store in database"""
        cursor = self.conn.cursor()
        hash_batch = []
        processed = 0
        errors = 0
        error_details = []

        logger.info(f"Starting hash computation for {len(files):,} files (batch_size={self.batch_size}, sha256={'enabled' if self.verify_sha256 else 'disabled'})")
        print(f"\nComputing hashes for {len(files):,} files...")
        print(f"Batch size: {self.batch_size}")
        print(f"SHA-256 verification: {'Enabled' if self.verify_sha256 else 'Disabled'}")
        print()

        for i, file_row in enumerate(files, 1):
            file_id = file_row['file_id']
            relative_path = file_row['path']
            file_size = file_row['size_bytes']
            mount_point = file_row['mount_point']

            # Construct absolute path
            if mount_point:
                # Convert mount_point (Z:/) to Windows format and join with relative path
                mount = mount_point.rstrip('/\\')
                file_path = f"{mount}\\{relative_path}"
            else:
                file_path = relative_path

            # Compute quick hash
            quick_hash, error = compute_quick_hash(file_path)

            if error:
                errors += 1
                error_details.append({'file': relative_path, 'error': error})
                if errors <= 10:
                    logger.warning(f"Failed to hash {relative_path}: {error}")
                elif errors == 11:
                    logger.warning("More than 10 hash errors, suppressing further individual error logs")
                continue

            # Optionally compute SHA-256
            sha256_hash = None
            if self.verify_sha256:
                sha256_hash, sha_error = compute_sha256(file_path)
                if sha_error:
                    logger.warning(f"Failed to compute SHA-256 for {file_path}: {sha_error}")

            # Add to batch
            hash_batch.append({
                'file_id': file_id,
                'scan_id': self.scan_id,
                'file_path': file_path,
                'file_size': file_size,
                'quick_hash': quick_hash,
                'sha256_hash': sha256_hash
            })

            processed += 1

            # Insert batch
            if len(hash_batch) >= self.batch_size:
                try:
                    self._insert_hash_batch(cursor, hash_batch)
                    self.conn.commit()
                except Exception as e:
                    logger.error(f"Failed to insert hash batch: {e}", exc_info=True)
                hash_batch = []

                # Progress report
                progress_pct = (i / len(files)) * 100
                if i % 10000 == 0:
                    logger.info(f"Progress: {i:,}/{len(files):,} ({progress_pct:.1f}%) - {errors} errors")
                print(f"Progress: {i:,}/{len(files):,} ({progress_pct:.1f}%) - {errors} errors")

        # Insert remaining
        if hash_batch:
            try:
                self._insert_hash_batch(cursor, hash_batch)
                self.conn.commit()
            except Exception as e:
                logger.error(f"Failed to insert final hash batch: {e}", exc_info=True)

        # Log summary
        logger.info(f"Hash computation complete: {processed:,} files processed, {errors} errors")
        if errors > 0:
            logger.warning(f"Total hash errors: {errors}")
            if errors <= 50:
                for err in error_details[:50]:
                    logger.debug(f"Error detail: {err['file']} - {err['error']}")

        print(f"\nCompleted: {processed:,} files hashed, {errors} errors")
        return processed, errors

    def _insert_hash_batch(self, cursor, hash_batch):
        """Insert a batch of hashes into database"""
        cursor.executemany('''
            INSERT INTO file_hashes (file_id, scan_id, file_path, file_size, quick_hash, sha256_hash)
            VALUES (:file_id, :scan_id, :file_path, :file_size, :quick_hash, :sha256_hash)
        ''', hash_batch)

    def detect_duplicates(self):
        """Detect duplicate groups based on quick_hash"""
        cursor = self.conn.cursor()

        logger.info("Starting duplicate detection")
        print("\nDetecting duplicate groups...")

        # Find files with matching quick_hash
        cursor.execute('''
            SELECT quick_hash, file_size, COUNT(*) as count
            FROM file_hashes
            WHERE scan_id = ? AND quick_hash IS NOT NULL
            GROUP BY quick_hash, file_size
            HAVING COUNT(*) > 1
            ORDER BY file_size * (COUNT(*) - 1) DESC
        ''', (self.scan_id,))

        duplicate_candidates = cursor.fetchall()

        if not duplicate_candidates:
            logger.info("No duplicates found")
            print("No duplicates found.")
            return 0

        logger.info(f"Found {len(duplicate_candidates):,} potential duplicate groups")
        print(f"Found {len(duplicate_candidates):,} potential duplicate groups")

        # Create duplicate groups
        groups_created = 0
        total_duplicates = 0

        for row in duplicate_candidates:
            quick_hash = row['quick_hash']
            file_size = row['file_size']
            member_count = row['count']
            wasted_bytes = file_size * (member_count - 1)

            # Create duplicate group
            cursor.execute('''
                INSERT INTO duplicate_groups (quick_hash, file_size, member_count, wasted_bytes, sha256_verified)
                VALUES (?, ?, ?, ?, ?)
            ''', (quick_hash, file_size, member_count, wasted_bytes, 0))

            group_id = cursor.lastrowid

            # Update file_hashes with group_id
            cursor.execute('''
                UPDATE file_hashes
                SET duplicate_group_id = ?
                WHERE scan_id = ? AND quick_hash = ? AND file_size = ?
            ''', (group_id, self.scan_id, quick_hash, file_size))

            groups_created += 1
            total_duplicates += (member_count - 1)

        self.conn.commit()

        logger.info(f"Created {groups_created:,} duplicate groups, total duplicate files: {total_duplicates:,}")
        print(f"Created {groups_created:,} duplicate groups")
        print(f"Total duplicate files: {total_duplicates:,}")

        return groups_created

    def generate_summary(self):
        """Generate summary statistics"""
        cursor = self.conn.cursor()

        # Total files hashed
        cursor.execute('SELECT COUNT(*) FROM file_hashes WHERE scan_id = ?', (self.scan_id,))
        total_hashed = cursor.fetchone()[0]

        # Total duplicates
        cursor.execute('''
            SELECT COUNT(*) FROM file_hashes
            WHERE scan_id = ? AND duplicate_group_id IS NOT NULL
        ''', (self.scan_id,))
        total_in_groups = cursor.fetchone()[0]

        # Wasted space
        cursor.execute('''
            SELECT SUM(wasted_bytes) FROM duplicate_groups
            WHERE group_id IN (
                SELECT DISTINCT duplicate_group_id FROM file_hashes WHERE scan_id = ?
            )
        ''', (self.scan_id,))
        wasted_bytes = cursor.fetchone()[0] or 0
        wasted_gb = wasted_bytes / (1024**3)

        # Top duplicate groups
        cursor.execute('''
            SELECT dg.quick_hash, dg.file_size, dg.member_count, dg.wasted_bytes,
                   fh.file_path
            FROM duplicate_groups dg
            JOIN file_hashes fh ON dg.group_id = fh.duplicate_group_id
            WHERE fh.scan_id = ?
            GROUP BY dg.group_id
            ORDER BY dg.wasted_bytes DESC
            LIMIT 10
        ''', (self.scan_id,))

        top_groups = cursor.fetchall()

        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)
        print(f"Total files hashed: {total_hashed:,}")
        print(f"Files in duplicate groups: {total_in_groups:,}")
        print(f"Total wasted space: {wasted_gb:.2f} GB")
        print()
        print("Top 10 duplicate groups by wasted space:")
        print(f"{'Size (MB)':>12} | {'Count':>6} | {'Wasted (MB)':>12} | Example")
        print("-" * 60)

        for row in top_groups:
            size_mb = row['file_size'] / (1024**2)
            wasted_mb = row['wasted_bytes'] / (1024**2)
            example_path = Path(row['file_path']).name
            print(f"{size_mb:12.2f} | {row['member_count']:6d} | {wasted_mb:12.2f} | {example_path}")

        print("="*60)


def main():
    parser = argparse.ArgumentParser(description='Populate file hashes for a scan')
    parser.add_argument('--scan-id', type=int, required=True, help='Scan ID to process')
    parser.add_argument('--db', default='output/archive.db', help='Database path')
    parser.add_argument('--verify-sha256', action='store_true', help='Also compute SHA-256 hashes')
    parser.add_argument('--batch-size', type=int, default=1000, help='Batch insert size')

    args = parser.parse_args()

    logger.info(f"Starting populate_hashes for scan_id {args.scan_id} (database={args.db})")
    print(f"Populating hashes for scan {args.scan_id}")
    print(f"Database: {args.db}")
    print()

    populator = HashPopulator(args.db, args.scan_id, args.verify_sha256, args.batch_size)

    try:
        populator.connect()

        # Get files to hash
        files = populator.get_files_to_hash()

        if not files:
            logger.info("No files need hashing")
            print("No files need hashing (already processed or scan is empty)")
            return 0

        # Compute and store hashes
        processed, errors = populator.compute_and_store_hashes(files)

        if processed == 0:
            logger.warning("No hashes computed")
            print("No hashes computed")
            return 1

        # Detect duplicates
        populator.detect_duplicates()

        # Generate summary
        populator.generate_summary()

        logger.info("Hash population completed successfully")
        return 0

    except Exception as e:
        logger.error(f"Fatal error in populate_hashes: {e}", exc_info=True)
        print(f"\nError: {e}")
        return 1

    finally:
        populator.close()
        logger.debug("Database connection closed")


if __name__ == '__main__':
    sys.exit(main())
