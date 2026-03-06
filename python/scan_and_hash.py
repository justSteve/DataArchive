#!/usr/bin/env python3
"""
Scan a drive and generate file hashes

This script extends the basic file scanner to include hash generation.
It adds quick_hash and sha256_hash fields to the database if they don't exist,
then scans the specified drive and generates hashes for all files.

Usage:
    python scan_and_hash.py Z:\ --sha256
"""

import sys
import argparse
import json
import sqlite3
from pathlib import Path
from datetime import datetime
from tqdm import tqdm

from core.logger import get_logger
from core.database import Database
from core.drive_manager import DriveManager
from core.file_scanner import FileScanner
from utils.hash_utils import hash_file
from utils.power_manager import prevent_sleep

logger = get_logger(__name__)


def add_hash_columns_if_needed(db: Database):
    """Add hash columns to files table if they don't exist"""
    with db.get_connection("add_hash_columns") as conn:
        cursor = conn.execute("PRAGMA table_info(files)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'quick_hash' not in columns:
            logger.info("Adding quick_hash column to files table...")
            conn.execute("ALTER TABLE files ADD COLUMN quick_hash TEXT")

        if 'sha256_hash' not in columns:
            logger.info("Adding sha256_hash column to files table...")
            conn.execute("ALTER TABLE files ADD COLUMN sha256_hash TEXT")

        if 'quick_hash' not in columns or 'sha256_hash' not in columns:
            logger.info("✓ Hash columns added to database")
        else:
            logger.info("✓ Hash columns already exist")


def insert_file_with_hash(db: Database, scan_id: int, file_info: dict, hash_result):
    """Insert a file record with hash information"""
    with db.get_connection("insert_file_with_hash") as conn:
        conn.execute("""
            INSERT INTO files (
                scan_id, path, size_bytes,
                modified_date, created_date, accessed_date,
                extension, is_hidden, is_system,
                quick_hash, sha256_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            scan_id,
            file_info['path'],
            file_info['size_bytes'],
            file_info['modified_date'],
            file_info['created_date'],
            file_info['accessed_date'],
            file_info['extension'],
            file_info['is_hidden'],
            file_info['is_system'],
            hash_result.quick_hash,
            hash_result.sha256_hash
        ))


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Scan a drive and generate file hashes'
    )
    parser.add_argument(
        'drive_path',
        help='Path to drive to scan (e.g., Z:\\)'
    )
    parser.add_argument(
        '--db',
        default='output/archive.db',
        help='Path to database file (default: output/archive.db)'
    )
    parser.add_argument(
        '--sha256',
        action='store_true',
        help='Compute SHA-256 hashes (slower but more accurate)'
    )
    parser.add_argument(
        '--no-progress',
        action='store_true',
        help='Disable progress bar'
    )
    parser.add_argument(
        '--drive-label',
        help='Label/name for this drive (e.g., "Backup Drive", "Manual Copy from G:")'
    )
    parser.add_argument(
        '--json-output',
        action='store_true',
        help='Output results as JSON'
    )

    args = parser.parse_args()

    # Validate drive path
    drive_path = Path(args.drive_path)
    if not drive_path.exists():
        if args.json_output:
            print(json.dumps({
                'success': False,
                'error': f"Drive path does not exist: {drive_path}",
                'status': 'failed'
            }))
        else:
            logger.error(f"Drive path does not exist: {drive_path}")
        return 1

    if not drive_path.is_dir():
        if args.json_output:
            print(json.dumps({
                'success': False,
                'error': f"Drive path is not a directory: {drive_path}",
                'status': 'failed'
            }))
        else:
            logger.error(f"Drive path is not a directory: {drive_path}")
        return 1

    logger.info("="*60)
    logger.info("DATA ARCHIVE SYSTEM - Scan with Hashing")
    logger.info("="*60)
    logger.info(f"Drive: {drive_path}")
    logger.info(f"Database: {args.db}")
    logger.info(f"SHA-256: {'Yes' if args.sha256 else 'No (quick hash only)'}")
    logger.info(f"Started: {datetime.now()}")
    logger.info("="*60)

    try:
        with prevent_sleep():
            # Initialize database
            db = Database(args.db)
            logger.info("✓ Database initialized")

            # Add hash columns if needed
            add_hash_columns_if_needed(db)

            # Get drive info
            logger.info("\n--- STAGE 1: Drive Discovery ---")
            drive_mgr = DriveManager()
            drive_info = drive_mgr.get_drive_info(str(drive_path))

            if not drive_info:
                logger.error("Could not get drive information")
                return 1

            logger.info(f"Drive accessible: {drive_info['accessible']}")
            logger.info(f"Total size: {drive_info['total_bytes'] / (1024**3):.2f} GB")
            logger.info(f"Free space: {drive_info['free_bytes'] / (1024**3):.2f} GB")

            # Create drive record
            drive_record = {
                'serial_number': drive_info.get('serial_number', f"MANUAL_{drive_path.name}"),
                'model': drive_info.get('model', f"Drive_{drive_path.name}"),
                'size_bytes': drive_info['total_bytes'],
                'filesystem': drive_info.get('filesystem'),
                'connection_type': drive_info.get('connection_method', drive_mgr.platform),
                'label': args.drive_label,
                'notes': f"Scanned with hashing on {datetime.now().isoformat()}"
            }
            drive_id = db.insert_drive(drive_record)
            logger.info(f"✓ Drive record created: ID {drive_id}")

            # Start scan session
            scan_id = db.start_scan(drive_id, str(drive_path))
            logger.info(f"✓ Scan session started: ID {scan_id}")

            # Scan and hash files
            logger.info("\n--- STAGE 2: File Scan with Hashing ---")
            if args.sha256:
                logger.info("Computing SHA-256 hashes (this will take longer)...")
            else:
                logger.info("Computing quick hashes (fast)...")

            scanner = FileScanner(str(drive_path))

            file_count = 0
            total_size = 0
            hash_errors = 0

            # Get file count for progress bar
            if not args.no_progress:
                total_files = scanner.count_files()
                pbar = tqdm(total=total_files, unit='files', desc='Scanning & Hashing')

            # Process files one by one
            for file_info in scanner.scan(show_progress=False):  # We have our own progress bar
                try:
                    # Get absolute path for hashing
                    abs_path = drive_path / file_info['path']

                    # Generate hash
                    hash_result = hash_file(str(abs_path), compute_sha256_hash=args.sha256)

                    if hash_result.error:
                        logger.debug(f"Hash error for {file_info['path']}: {hash_result.error}")
                        hash_errors += 1

                    # Insert file with hash
                    insert_file_with_hash(db, scan_id, file_info, hash_result)

                    file_count += 1
                    total_size += file_info['size_bytes']

                    if not args.no_progress:
                        pbar.update(1)

                except Exception as e:
                    logger.error(f"Error processing {file_info.get('path', 'unknown')}: {e}")
                    hash_errors += 1
                    if not args.no_progress:
                        pbar.update(1)

            if not args.no_progress:
                pbar.close()

            logger.info(f"✓ Scan complete: {file_count:,} files")
            logger.info(f"  Total size: {total_size / (1024**3):.2f} GB")
            logger.info(f"  Hash errors: {hash_errors}")

            # Complete scan
            db.complete_scan(scan_id, file_count, total_size)

            # Output results
            if args.json_output:
                result = {
                    'success': True,
                    'scan_id': scan_id,
                    'drive_id': drive_id,
                    'file_count': file_count,
                    'total_size': total_size,
                    'hash_errors': hash_errors,
                    'status': 'complete',
                    'db_path': args.db,
                    'drive_path': str(drive_path),
                    'completed_at': datetime.now().isoformat()
                }
                print(json.dumps(result))
            else:
                logger.info("\n" + "="*60)
                logger.info("SCAN WITH HASHING COMPLETE!")
                logger.info("="*60)
                logger.info(f"Scan ID: {scan_id}")
                logger.info(f"Files cataloged: {file_count:,}")
                logger.info(f"Database: {args.db}")
                logger.info(f"Completed: {datetime.now()}")
                logger.info("="*60)

        return 0

    except KeyboardInterrupt:
        if args.json_output:
            print(json.dumps({
                'success': False,
                'error': 'Scan interrupted by user',
                'status': 'interrupted'
            }))
        else:
            logger.warning("\n\nScan interrupted by user")
        return 130
    except Exception as e:
        if args.json_output:
            print(json.dumps({
                'success': False,
                'error': str(e),
                'status': 'failed'
            }))
        else:
            logger.error(f"\n\nError during scan: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
