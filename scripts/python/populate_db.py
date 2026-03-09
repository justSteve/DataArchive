#!/usr/bin/env python3
"""
Compute and store file hashes for a scan.
Matches the actual database schema.
"""

import sys
import sqlite3
import time
from pathlib import Path
from datetime import datetime

# Add python directory to path
sys.path.insert(0, str(Path(__file__).parent / 'python'))

from utils.hash_utils import compute_quick_hash, compute_sha256
from core.logger import get_logger
from core.progress_reporter import ProgressReporter

logger = get_logger(__name__)


def compute_hashes(scan_id, db_path='output/archive.db', batch_size=500, verify_sha256=False):
    """Compute hashes for all files in a scan"""
    logger.info(f"Starting hash computation for scan_id {scan_id}")

    try:
        conn = sqlite3.connect(db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
    except sqlite3.Error as e:
        logger.error(f"Failed to connect to database: {e}", exc_info=True)
        return 0, 0

    try:
        # Get files that don't have hashes yet
        cursor.execute('''
            SELECT f.file_id, f.path, f.size_bytes, s.mount_point
            FROM files f
            JOIN scans s ON f.scan_id = s.scan_id
            WHERE f.scan_id = ?
              AND NOT EXISTS (
                SELECT 1 FROM file_hashes WHERE file_id = f.file_id AND hash_type = 'quick_hash'
              )
            ORDER BY f.file_id
        ''', (scan_id,))

        files = cursor.fetchall()
        total = len(files)

        if total == 0:
            logger.info("No files need hashing")
            print("No files need hashing")
            return 0, 0

        logger.info(f"Found {total:,} files to hash (batch_size={batch_size}, sha256={'enabled' if verify_sha256 else 'disabled'})")
        print(f"\nComputing hashes for {total:,} files")
        print(f"Batch size: {batch_size}")
        print(f"SHA-256: {'Enabled' if verify_sha256 else 'Disabled'}\n")

    except sqlite3.Error as e:
        logger.error(f"Failed to query files for hashing: {e}", exc_info=True)
        conn.close()
        return 0, 0

    hash_batch = []
    processed = 0
    errors = 0
    error_details = []  # Track error details for logging

    # Initialize progress reporter
    progress = ProgressReporter('hash_computation', str(scan_id), total)

    for i, row in enumerate(files, 1):
        file_id = row['file_id']
        relative_path = row['path']
        file_size = row['size_bytes']
        mount_point = row['mount_point'] or ''

        # Construct absolute path
        mount = mount_point.rstrip('/\\')
        file_path = f"{mount}\\{relative_path}" if mount else relative_path

        # Compute quick hash
        quick_hash, error = compute_quick_hash(file_path)

        if error:
            errors += 1
            error_details.append({'file': relative_path, 'error': error})
            if errors <= 10:
                logger.warning(f"Hash error for {Path(relative_path).name}: {error}")
                print(f"  Error: {Path(relative_path).name}: {error}")
            elif errors == 11:
                logger.warning(f"More than 10 hash errors, suppressing further individual error logs")
            continue

        # Add quick_hash to batch
        hash_batch.append({
            'scan_id': scan_id,
            'file_id': file_id,
            'hash_type': 'quick_hash',
            'hash_value': quick_hash,
            'computed_at': datetime.now().isoformat()
        })

        # Optionally compute SHA-256
        if verify_sha256:
            sha256_hash, sha_error = compute_sha256(file_path)
            if not sha_error:
                hash_batch.append({
                    'scan_id': scan_id,
                    'file_id': file_id,
                    'hash_type': 'sha256',
                    'hash_value': sha256_hash,
                    'computed_at': datetime.now().isoformat()
                })

        processed += 1

        # Insert batch with retry logic
        if len(hash_batch) >= batch_size:
            retry_count = 0
            max_retries = 3

            while retry_count < max_retries:
                try:
                    cursor.executemany('''
                        INSERT INTO file_hashes (scan_id, file_id, hash_type, hash_value, computed_at)
                        VALUES (:scan_id, :file_id, :hash_type, :hash_value, :computed_at)
                    ''', hash_batch)
                    conn.commit()
                    break  # Success
                except sqlite3.IntegrityError as e:
                    logger.error(f"Duplicate key in hash batch: {e}")
                    # Continue processing - these may be duplicates from a previous run
                    break
                except sqlite3.OperationalError as e:
                    if "locked" in str(e).lower():
                        retry_count += 1
                        if retry_count < max_retries:
                            logger.warning(f"Database locked, retrying ({retry_count}/{max_retries})...")
                            time.sleep(1 * retry_count)  # Exponential backoff
                        else:
                            logger.error(f"Database locked after {max_retries} retries, skipping batch")
                            break
                    else:
                        logger.error(f"Database error inserting hash batch: {e}", exc_info=True)
                        break

            hash_batch = []

            pct = (i / total) * 100
            if i % 10000 == 0:
                logger.info(f"Progress: {i:,}/{total:,} ({pct:.1f}%) - {errors} errors")
            print(f"  Progress: {i:,}/{total:,} ({pct:.1f}%) - {errors} errors")

            # Report progress every batch
            progress.report(
                processed=i,
                message=f"Hashing files: {i:,}/{total:,}",
                details={"errors": errors, "batch_number": i // batch_size}
            )

    # Insert remaining with retry
    if hash_batch:
        try:
            cursor.executemany('''
                INSERT INTO file_hashes (scan_id, file_id, hash_type, hash_value, computed_at)
                VALUES (:scan_id, :file_id, :hash_type, :hash_value, :computed_at)
            ''', hash_batch)
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to insert final hash batch: {e}", exc_info=True)

    conn.close()

    # Report completion
    progress.complete(f"Hashed {processed:,} files with {errors} errors")

    # Log summary
    logger.info(f"Hash computation complete: {processed:,} files processed, {errors} errors")
    if errors > 0:
        logger.warning(f"Total errors: {errors}")
        if errors <= 50:
            # Log first 50 error details
            for err in error_details[:50]:
                logger.debug(f"Error detail: {err['file']} - {err['error']}")

    print(f"\nCompleted: {processed:,} files hashed, {errors} errors\n")
    return processed, errors


def detect_duplicates(scan_id, db_path='output/archive.db'):
    """Find duplicate files and populate duplicate_groups and duplicate_members"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("Detecting duplicates...")

    # Find quick_hash values that appear more than once
    cursor.execute('''
        SELECT
            fh.hash_value,
            f.size_bytes,
            COUNT(*) as count
        FROM file_hashes fh
        JOIN files f ON fh.file_id = f.file_id
        WHERE fh.scan_id = ? AND fh.hash_type = 'quick_hash'
        GROUP BY fh.hash_value, f.size_bytes
        HAVING COUNT(*) > 1
        ORDER BY f.size_bytes * (COUNT(*) - 1) DESC
    ''', (scan_id,))

    duplicate_candidates = cursor.fetchall()

    if not duplicate_candidates:
        print("No duplicates found")
        conn.close()
        return 0

    print(f"Found {len(duplicate_candidates):,} duplicate groups\n")

    groups_created = 0

    for row in duplicate_candidates:
        hash_value = row['hash_value']
        file_size = row['size_bytes']
        file_count = row['count']
        wasted_bytes = file_size * (file_count - 1)

        # Create duplicate group
        cursor.execute('''
            INSERT INTO duplicate_groups (hash_value, file_size, file_count, total_wasted_bytes, created_at, status)
            VALUES (?, ?, ?, ?, ?, 'unresolved')
        ''', (hash_value, file_size, file_count, wasted_bytes, datetime.now().isoformat()))

        group_id = cursor.lastrowid

        # Find all files with this hash
        cursor.execute('''
            SELECT fh.file_id, fh.scan_id
            FROM file_hashes fh
            WHERE fh.hash_value = ? AND fh.hash_type = 'quick_hash' AND fh.scan_id = ?
        ''', (hash_value, scan_id))

        members = cursor.fetchall()

        # Add members (first one marked as primary)
        for idx, member in enumerate(members):
            is_primary = (idx == 0)
            cursor.execute('''
                INSERT INTO duplicate_members (group_id, file_id, scan_id, is_primary)
                VALUES (?, ?, ?, ?)
            ''', (group_id, member['file_id'], member['scan_id'], is_primary))

        groups_created += 1

    conn.commit()
    conn.close()

    print(f"Created {groups_created:,} duplicate groups")
    return groups_created


def show_summary(scan_id, db_path='output/archive.db'):
    """Show summary of duplicates"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Total hashed
    cursor.execute('SELECT COUNT(*) FROM file_hashes WHERE scan_id = ? AND hash_type = "quick_hash"', (scan_id,))
    total_hashed = cursor.fetchone()[0]

    # Total in duplicate groups
    cursor.execute('''
        SELECT COUNT(DISTINCT dm.file_id)
        FROM duplicate_members dm
        WHERE dm.scan_id = ?
    ''', (scan_id,))
    total_in_groups = cursor.fetchone()[0]

    # Total wasted space
    cursor.execute('''
        SELECT SUM(dg.total_wasted_bytes)
        FROM duplicate_groups dg
        JOIN duplicate_members dm ON dg.group_id = dm.group_id
        WHERE dm.scan_id = ?
    ''', (scan_id,))
    wasted_bytes = cursor.fetchone()[0] or 0
    wasted_gb = wasted_bytes / (1024**3)

    # Top groups
    cursor.execute('''
        SELECT dg.group_id, dg.file_size, dg.file_count, dg.total_wasted_bytes,
               f.path
        FROM duplicate_groups dg
        JOIN duplicate_members dm ON dg.group_id = dm.group_id
        JOIN files f ON dm.file_id = f.file_id
        WHERE dm.scan_id = ? AND dm.is_primary = 1
        ORDER BY dg.total_wasted_bytes DESC
        LIMIT 15
    ''', (scan_id,))

    top_groups = cursor.fetchall()

    print("\n" + "="*70)
    print("DUPLICATE DETECTION SUMMARY")
    print("="*70)
    print(f"Total files hashed: {total_hashed:,}")
    print(f"Files in duplicate groups: {total_in_groups:,}")
    print(f"Total wasted space: {wasted_gb:.2f} GB ({wasted_bytes:,} bytes)")
    print()
    print("Top 15 duplicate groups by wasted space:")
    print(f"{'Size (MB)':>12} | {'Count':>6} | {'Wasted (MB)':>12} | Example file")
    print("-" * 70)

    for row in top_groups:
        size_mb = row['file_size'] / (1024**2)
        wasted_mb = row['total_wasted_bytes'] / (1024**2)
        example = Path(row['path']).name[:40]
        print(f"{size_mb:12.2f} | {row['file_count']:6d} | {wasted_mb:12.2f} | {example}")

    print("="*70)

    conn.close()


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Compute hashes and detect duplicates')
    parser.add_argument('--scan-id', type=int, required=True, help='Scan ID to process')
    parser.add_argument('--db', default='output/archive.db', help='Database path')
    parser.add_argument('--batch-size', type=int, default=500, help='Batch size')
    parser.add_argument('--verify-sha256', action='store_true', help='Also compute SHA-256')
    parser.add_argument('--skip-hashing', action='store_true', help='Skip hashing (only detect duplicates)')

    args = parser.parse_args()

    if not args.skip_hashing:
        processed, errors = compute_hashes(args.scan_id, args.db, args.batch_size, args.verify_sha256)
        if processed == 0:
            sys.exit(1)

    groups = detect_duplicates(args.scan_id, args.db)
    show_summary(args.scan_id, args.db)
