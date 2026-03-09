#!/usr/bin/env python
"""Scan G: drive into database."""
import sys
sys.path.insert(0, 'python')

from core.database import Database
from core.file_scanner import FileScanner
from core.logger import get_logger
import sqlite3

logger = get_logger(__name__)

def main():
    logger.info("Starting G: drive scan")

    try:
        db = Database('output/archive.db')
    except (FileNotFoundError, sqlite3.Error) as e:
        logger.error(f"Failed to open database: {e}", exc_info=True)
        print(f"Error: Could not open database - {e}")
        sys.exit(1)

    try:
        # G: partition - same physical drive, different partition
        drive_info = {
            'serial_number': 'WD-WCAW33155798-G',
            'model': 'WDC WD1002FAEX-00Y9A0 (G:)',
            'manufacturer': 'Western Digital',
            'size_bytes': 308151316480,
            'filesystem': 'NTFS',
            'connection_type': 'SATA',
            'media_type': 'HDD',
            'bus_type': 'SATA'
        }

        drive_id = db.insert_drive(drive_info)
        logger.info(f"Drive registered with ID: {drive_id}")
        print(f'Drive ID: {drive_id}')

        scan_id = db.start_scan(drive_id, 'G:\\')
        logger.info(f"Scan started with ID: {scan_id}")
        print(f'Scan ID: {scan_id}')

        scanner = FileScanner('G:\\')
        file_count = 0
        total_size = 0
        batch = []
        BATCH_SIZE = 1000

        logger.info("Beginning file enumeration")
        print('Scanning G: drive...')

        for file_info in scanner.scan():
            batch.append(file_info)
            file_count += 1
            total_size += file_info.get('size_bytes', 0)

            if len(batch) >= BATCH_SIZE:
                db.insert_files_batch(scan_id, batch)
                batch = []
                if file_count % 10000 == 0:
                    logger.info(f"Progress: {file_count:,} files scanned")
                    print(f'  {file_count:,} files...')

        # Insert remaining files
        if batch:
            db.insert_files_batch(scan_id, batch)
            logger.debug(f"Inserted final batch of {len(batch)} files")

        db.complete_scan(scan_id, file_count, total_size)
        logger.info(f"Scan complete: {file_count:,} files, {total_size / (1024**3):.2f} GB")
        print(f'Scan complete: {file_count:,} files, {total_size:,} bytes')

    except KeyboardInterrupt:
        logger.warning("Scan interrupted by user")
        print("\nScan interrupted by user")
        sys.exit(0)

    except sqlite3.Error as e:
        logger.error(f"Database error during scan: {e}", exc_info=True)
        print(f"Database error: {e}")
        sys.exit(1)

    except Exception as e:
        logger.error(f"Unexpected error during scan: {e}", exc_info=True)
        print(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
