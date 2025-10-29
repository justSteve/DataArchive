#!/usr/bin/env python3
"""
Main script to scan a drive and catalog all files

Usage:
    python scan_drive.py /mnt/e
    python scan_drive.py /path/to/drive
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime

from core.logger import get_logger
from core.database import Database
from core.drive_manager import DriveManager
from core.drive_validator import DriveValidator
from core.os_detector import OSDetector
from core.file_scanner import FileScanner
from utils.power_manager import prevent_sleep

logger = get_logger(__name__)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Scan and catalog a drive'
    )
    parser.add_argument(
        'drive_path',
        help='Path to drive to scan (e.g., /mnt/e)'
    )
    parser.add_argument(
        '--db',
        default='output/archive.db',
        help='Path to database file (default: output/archive.db)'
    )
    parser.add_argument(
        '--no-progress',
        action='store_true',
        help='Disable progress bar'
    )
    parser.add_argument(
        '--drive-model',
        help='Manually specify drive model (e.g., "Samsung 870 EVO 250GB")'
    )
    parser.add_argument(
        '--drive-serial',
        help='Manually specify drive serial number'
    )
    parser.add_argument(
        '--drive-notes',
        help='Additional notes about the drive (e.g., "Physical label: Blue sticker")'
    )
    
    args = parser.parse_args()
    
    # Validate drive path
    drive_path = Path(args.drive_path)
    if not drive_path.exists():
        logger.error(f"Drive path does not exist: {drive_path}")
        return 1
    
    if not drive_path.is_dir():
        logger.error(f"Drive path is not a directory: {drive_path}")
        return 1
    
    logger.info("="*60)
    logger.info("DATA ARCHIVE SYSTEM - Drive Scan")
    logger.info("="*60)
    logger.info(f"Drive: {drive_path}")
    logger.info(f"Database: {args.db}")
    logger.info(f"Started: {datetime.now()}")
    logger.info("="*60)
    
    try:
        # Prevent system sleep during the scan
        # Similar to C#'s using statement - automatically restored when done
        with prevent_sleep():
            # STAGE 0: Drive Validation
            logger.info("\n--- STAGE 0: Drive Validation ---")
            validator = DriveValidator(str(drive_path))
            validation_results = validator.validate()
            validator.print_validation_report(validation_results)
            
            # Stop if validation failed
            if not validation_results['valid']:
                logger.error("\nCannot proceed with scan due to validation errors.")
                logger.error("Please fix the errors above and try again.")
                return 1
            
            # Warn but continue if there are warnings
            if validation_results['warnings']:
                logger.warning("\nProceeding with scan despite warnings...\n")
            
            # Initialize database
            db = Database(args.db)
            logger.info("✓ Database initialized")
            
            # Initialize drive manager
            drive_mgr = DriveManager()
            
            # Get drive info
            logger.info("\n--- STAGE 1: Drive Discovery ---")
            drive_info = drive_mgr.get_drive_info(str(drive_path))
            if not drive_info:
                logger.error("Could not get drive information")
                return 1
            
            logger.info(f"Drive accessible: {drive_info['accessible']}")
            logger.info(f"Total size: {drive_info['total_bytes'] / (1024**3):.2f} GB")
            logger.info(f"Free space: {drive_info['free_bytes'] / (1024**3):.2f} GB")
            logger.info(f"Filesystem: {drive_info.get('filesystem', 'Unknown')}")
            
            # Use manual override if provided, otherwise use auto-detected
            if args.drive_model or args.drive_serial:
                logger.info("")
                logger.info("Using MANUALLY SPECIFIED drive identity:")
                if args.drive_model:
                    logger.info(f"  Model: {args.drive_model}")
                if args.drive_serial:
                    logger.info(f"  Serial: {args.drive_serial}")
                if args.drive_notes:
                    logger.info(f"  Notes: {args.drive_notes}")
            else:
                logger.info(f"Drive Model: {drive_info.get('model', 'Unknown')}")
                logger.info(f"Serial Number: {drive_info.get('serial_number', 'Unknown')}")
                logger.info(f"Connection: {drive_info.get('connection_method', 'Unknown')}")
            
            # Create drive record using manual override or auto-detected identity
            drive_record = {
                'serial_number': args.drive_serial or drive_info.get('serial_number', f"MANUAL_{drive_path.name}"),
                'model': args.drive_model or drive_info.get('model', f"Drive_{drive_path.name}"),
                'size_bytes': drive_info['total_bytes'],
                'filesystem': drive_info.get('filesystem'),
                'connection_type': drive_info.get('connection_method', drive_mgr.platform),
                'manufacturer': drive_info.get('manufacturer'),
                'firmware_version': drive_info.get('firmware_version'),
                'media_type': drive_info.get('media_type'),
                'bus_type': drive_info.get('bus_type'),
                'notes': args.drive_notes
            }
            drive_id = db.insert_drive(drive_record)
            logger.info(f"✓ Drive record created: ID {drive_id}")
            
            # Start scan session
            scan_id = db.start_scan(drive_id, str(drive_path))
            logger.info(f"✓ Scan session started: ID {scan_id}")
            
            # Stage 2: OS Detection
            logger.info("\n--- STAGE 2: OS Detection ---")
            os_detector = OSDetector(str(drive_path))
            os_info = os_detector.detect()
            
            logger.info(f"OS Type: {os_info['os_type']}")
            logger.info(f"OS Name: {os_info['os_name']}")
            logger.info(f"Detection Method: {os_info.get('detection_method', 'N/A')}")
            logger.info(f"Confidence: {os_info['confidence']}")
            logger.info(f"Boot Capable: {os_info['boot_capable']}")
            
            db.insert_os_info(scan_id, os_info)
            logger.info("✓ OS info saved")
            
            # Stage 3: File Scan
            logger.info("\n--- STAGE 3: Full File Scan ---")
            logger.info("This may take 10-30 minutes for large drives...")
            
            scanner = FileScanner(str(drive_path))
            
            file_count = 0
            total_size = 0
            batch = []
            batch_size = 1000
            
            for file_info in scanner.scan(show_progress=not args.no_progress):
                batch.append(file_info)
                file_count += 1
                total_size += file_info['size_bytes']
                
                # Batch insert
                if len(batch) >= batch_size:
                    db.insert_files_batch(scan_id, batch)
                    batch = []
            
            # Insert remaining
            if batch:
                db.insert_files_batch(scan_id, batch)
            
            logger.info(f"✓ File scan complete: {file_count:,} files")
            logger.info(f"  Total size: {total_size / (1024**3):.2f} GB")
            
            # Complete scan
            db.complete_scan(scan_id, file_count, total_size)
            
            # Stage 4: Generate Statistics
            logger.info("\n--- STAGE 4: Analysis & Statistics ---")
            stats = scanner.get_statistics(scan_id, db)
            if stats:
                logger.info(f"Oldest file: {stats.get('oldest_file_date', 'N/A')}")
                logger.info(f"Newest file: {stats.get('newest_file_date', 'N/A')}")
                logger.info(f"Largest file: {stats.get('largest_file_size', 0) / (1024**2):.2f} MB")
                logger.info(f"Most common extension: {stats.get('most_common_extension', 'N/A')}")
            
            logger.info("\n" + "="*60)
            logger.info("SCAN COMPLETE!")
            logger.info("="*60)
            logger.info(f"Scan ID: {scan_id}")
            logger.info(f"Files cataloged: {file_count:,}")
            logger.info(f"Database: {args.db}")
            logger.info(f"Completed: {datetime.now()}")
            logger.info("="*60)
            
            logger.info("\nNext steps:")
            logger.info("  1. View results: sqlite3 output/archive.db")
            logger.info("  2. Launch archive UI: python archive_ui.py")
        
        # Sleep prevention automatically restored here
        return 0
        
    except KeyboardInterrupt:
        logger.warning("\n\nScan interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"\n\nError during scan: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
