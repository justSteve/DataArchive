"""
Pass 3: Metadata Capture with Duplicate Detection

Performs comprehensive file metadata capture:
- Full folder/file enumeration with progress reporting
- Quick hash computation for fast duplicate detection
- Optional SHA-256 for definitive duplicate confirmation
- Cross-scan duplicate detection using existing files table
- Generates JSON report with file statistics and duplicate summary
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional, List, Iterator, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.logger import get_logger
from core.database import Database
from core.file_scanner import FileScanner
from utils.hash_utils import (
    compute_quick_hash,
    compute_sha256,
    generate_composite_key,
    HashResult,
    hash_file
)

logger = get_logger(__name__)

# Configuration defaults
DEFAULT_MIN_SIZE_FOR_DUPLICATE = 1024  # Skip very small files for duplicate detection
DEFAULT_BATCH_SIZE = 500  # Database batch insert size


@dataclass
class DuplicateInfo:
    """Information about a duplicate file"""
    file_id: int
    scan_id: int
    path: str
    size_bytes: int
    quick_hash: str
    sha256_hash: Optional[str] = None
    drive_model: Optional[str] = None
    is_cross_scan: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'file_id': self.file_id,
            'scan_id': self.scan_id,
            'path': self.path,
            'size_bytes': self.size_bytes,
            'quick_hash': self.quick_hash,
            'sha256_hash': self.sha256_hash,
            'drive_model': self.drive_model,
            'is_cross_scan': self.is_cross_scan
        }


@dataclass
class DuplicateGroup:
    """A group of duplicate files"""
    group_id: Optional[int] = None
    quick_hash: str = ""
    file_size: int = 0
    members: List[DuplicateInfo] = field(default_factory=list)
    sha256_verified: bool = False
    wasted_bytes: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'group_id': self.group_id,
            'quick_hash': self.quick_hash,
            'file_size': self.file_size,
            'member_count': len(self.members),
            'members': [m.to_dict() for m in self.members],
            'sha256_verified': self.sha256_verified,
            'wasted_bytes': self.wasted_bytes
        }


@dataclass
class MetadataReport:
    """Complete metadata capture report for a drive"""
    drive_path: str = ""
    drive_letter: str = ""
    inspection_time: str = ""
    scan_id: Optional[int] = None

    # File statistics
    total_files: int = 0
    total_folders: int = 0
    total_size_bytes: int = 0
    files_processed: int = 0
    files_hashed: int = 0
    files_skipped: int = 0
    errors_count: int = 0

    # Extension breakdown
    extension_counts: Dict[str, int] = field(default_factory=dict)
    extension_sizes: Dict[str, int] = field(default_factory=dict)

    # Date range
    oldest_file_date: Optional[str] = None
    newest_file_date: Optional[str] = None

    # Size distribution
    largest_file_size: int = 0
    largest_file_path: str = ""
    size_distribution: Dict[str, int] = field(default_factory=dict)

    # Duplicate detection results
    duplicate_groups_found: int = 0
    total_duplicate_files: int = 0
    total_wasted_bytes: int = 0
    cross_scan_duplicates: int = 0
    duplicate_groups: List[Dict[str, Any]] = field(default_factory=list)

    # Status
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'drive_path': self.drive_path,
            'drive_letter': self.drive_letter,
            'inspection_time': self.inspection_time,
            'scan_id': self.scan_id,
            'total_files': self.total_files,
            'total_folders': self.total_folders,
            'total_size_bytes': self.total_size_bytes,
            'files_processed': self.files_processed,
            'files_hashed': self.files_hashed,
            'files_skipped': self.files_skipped,
            'errors_count': self.errors_count,
            'extension_counts': self.extension_counts,
            'extension_sizes': self.extension_sizes,
            'oldest_file_date': self.oldest_file_date,
            'newest_file_date': self.newest_file_date,
            'largest_file_size': self.largest_file_size,
            'largest_file_path': self.largest_file_path,
            'size_distribution': self.size_distribution,
            'duplicate_groups_found': self.duplicate_groups_found,
            'total_duplicate_files': self.total_duplicate_files,
            'total_wasted_bytes': self.total_wasted_bytes,
            'cross_scan_duplicates': self.cross_scan_duplicates,
            'duplicate_groups': self.duplicate_groups,
            'errors': self.errors,
            'warnings': self.warnings,
            'recommendations': self.recommendations,
            'summary': self.summary
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), indent=indent, default=str)


class MetadataCapture:
    """
    Metadata capture for Pass 3 of the multi-pass inspection workflow.

    Performs comprehensive file cataloging:
    1. Enumerate all files and folders with metadata
    2. Compute quick hashes for duplicate detection
    3. Identify duplicate groups within scan
    4. Find cross-scan duplicates from previous inspections
    5. Optionally verify duplicates with SHA-256

    Generates a JSON report suitable for Claude analysis.
    """

    def __init__(self, db_path: Optional[str] = None,
                 min_duplicate_size: int = DEFAULT_MIN_SIZE_FOR_DUPLICATE,
                 batch_size: int = DEFAULT_BATCH_SIZE):
        """
        Initialize the metadata capture inspector.

        Args:
            db_path: Path to SQLite database for storing results
            min_duplicate_size: Minimum file size for duplicate detection
            batch_size: Database batch insert size
        """
        self.db = Database(db_path) if db_path else None
        self.min_duplicate_size = min_duplicate_size
        self.batch_size = batch_size
        logger.info(f"MetadataCapture initialized (min_dup_size={min_duplicate_size})")

    def _extract_drive_letter(self, drive_path: str) -> Optional[str]:
        """Extract Windows drive letter from path"""
        import re
        if len(drive_path) >= 1 and drive_path[1:2] == ':':
            return drive_path[0].upper()
        match = re.match(r'^/mnt/([a-zA-Z])(?:/|$)', drive_path)
        if match:
            return match.group(1).upper()
        return None

    def _classify_size(self, size_bytes: int) -> str:
        """Classify file size into buckets"""
        if size_bytes < 1024:
            return "tiny (<1KB)"
        elif size_bytes < 1024 * 1024:
            return "small (1KB-1MB)"
        elif size_bytes < 100 * 1024 * 1024:
            return "medium (1MB-100MB)"
        elif size_bytes < 1024 * 1024 * 1024:
            return "large (100MB-1GB)"
        else:
            return "huge (>1GB)"

    def inspect(self, drive_path: str, session_id: Optional[int] = None,
                scan_id: Optional[int] = None,
                enable_hashing: bool = True,
                verify_with_sha256: bool = False,
                show_progress: bool = True,
                progress_callback: Optional[callable] = None) -> MetadataReport:
        """
        Perform complete metadata capture inspection on a drive.

        Args:
            drive_path: Path to the drive (e.g., '/mnt/d', 'D:')
            session_id: Optional inspection session ID for database recording
            scan_id: Optional scan_id to use (creates new if not provided)
            enable_hashing: Compute quick hashes for duplicate detection
            verify_with_sha256: Also compute SHA-256 for duplicate groups
            show_progress: Show progress bar
            progress_callback: Optional callback(current, total, message) for progress

        Returns:
            MetadataReport with complete capture results
        """
        report = MetadataReport()
        report.drive_path = drive_path
        report.drive_letter = self._extract_drive_letter(drive_path) or "?"
        report.inspection_time = datetime.now().isoformat()

        logger.info(f"Starting metadata capture for drive {report.drive_letter}: ({drive_path})")

        # Mark pass as started in database
        if self.db and session_id:
            self.db.start_pass(session_id, 3)

        # Get or create scan_id
        if self.db:
            if scan_id is None:
                # Get drive_id from session if available
                drive_id = None
                if session_id:
                    inspection = self.db.get_inspection(session_id)
                    if inspection:
                        drive_id = inspection.get('drive_id')

                if drive_id:
                    scan_id = self.db.start_scan(drive_id, drive_path)
                else:
                    # Create a temporary drive entry
                    drive_id = self.db.insert_drive({
                        'serial_number': f'TEMP-{datetime.now().strftime("%Y%m%d%H%M%S")}',
                        'model': f'Drive at {drive_path}'
                    })
                    scan_id = self.db.start_scan(drive_id, drive_path)

            report.scan_id = scan_id

        # Phase 1: File enumeration and metadata capture
        logger.info("Phase 1: Enumerating files and capturing metadata...")
        self._capture_file_metadata(drive_path, report, scan_id, show_progress, progress_callback)

        # Phase 2: Compute hashes for duplicate detection
        if enable_hashing and self.db and scan_id:
            logger.info("Phase 2: Computing hashes for duplicate detection...")
            self._compute_file_hashes(drive_path, report, scan_id, show_progress, progress_callback)

            # Phase 3: Identify duplicate groups
            logger.info("Phase 3: Identifying duplicate groups...")
            self._identify_duplicates(report, scan_id, verify_with_sha256)

        # Phase 4: Check for cross-scan duplicates
        if self.db and scan_id:
            logger.info("Phase 4: Checking for cross-scan duplicates...")
            self._find_cross_scan_duplicates(report, scan_id)

        # Generate recommendations
        report.recommendations.extend(self._generate_recommendations(report))

        # Generate summary
        report.summary = self._generate_summary(report)

        # Mark scan as complete
        if self.db and scan_id:
            self.db.complete_scan(scan_id, report.files_processed, report.total_size_bytes)

        # Store pass results in database
        if self.db and session_id:
            try:
                self.db.complete_pass(
                    session_id, 3,
                    report_json=report.to_json(),
                    error_message='; '.join(report.errors) if report.errors else None
                )
                logger.info(f"Metadata capture results saved to database (session {session_id})")
            except Exception as e:
                logger.error(f"Failed to save results to database: {e}")

        logger.info(f"Metadata capture complete: {report.files_processed:,} files, "
                    f"{report.duplicate_groups_found} duplicate groups")
        return report

    def _capture_file_metadata(self, drive_path: str, report: MetadataReport,
                                scan_id: Optional[int], show_progress: bool,
                                progress_callback: Optional[callable]) -> None:
        """Capture file metadata and store in database"""
        scanner = FileScanner(drive_path)
        files_batch = []
        folder_count = 0
        oldest_date = None
        newest_date = None

        # Track seen directories
        seen_dirs = set()

        try:
            for file_info in scanner.scan(show_progress=show_progress):
                report.files_processed += 1
                report.total_size_bytes += file_info['size_bytes']

                # Track extension stats
                ext = file_info['extension'] or '(no extension)'
                report.extension_counts[ext] = report.extension_counts.get(ext, 0) + 1
                report.extension_sizes[ext] = report.extension_sizes.get(ext, 0) + file_info['size_bytes']

                # Track size distribution
                size_class = self._classify_size(file_info['size_bytes'])
                report.size_distribution[size_class] = report.size_distribution.get(size_class, 0) + 1

                # Track largest file
                if file_info['size_bytes'] > report.largest_file_size:
                    report.largest_file_size = file_info['size_bytes']
                    report.largest_file_path = file_info['path']

                # Track date range
                mod_date = file_info.get('modified_date')
                if mod_date:
                    if oldest_date is None or mod_date < oldest_date:
                        oldest_date = mod_date
                    if newest_date is None or mod_date > newest_date:
                        newest_date = mod_date

                # Count unique directories
                dir_path = os.path.dirname(file_info['path'])
                if dir_path and dir_path not in seen_dirs:
                    seen_dirs.add(dir_path)
                    folder_count += 1

                # Batch for database
                if self.db and scan_id:
                    files_batch.append(file_info)
                    if len(files_batch) >= self.batch_size:
                        self.db.insert_files_batch(scan_id, files_batch)
                        files_batch = []

                # Progress callback
                if progress_callback and report.files_processed % 1000 == 0:
                    progress_callback(
                        report.files_processed, -1,
                        f"Processed {report.files_processed:,} files..."
                    )

        except Exception as e:
            report.errors.append(f"File enumeration error: {e}")
            logger.error(f"File enumeration error: {e}")

        # Insert remaining files
        if self.db and scan_id and files_batch:
            self.db.insert_files_batch(scan_id, files_batch)

        report.total_files = report.files_processed
        report.total_folders = folder_count
        report.files_skipped = scanner.skipped_count
        report.errors_count = scanner.error_count

        if oldest_date:
            report.oldest_file_date = oldest_date.isoformat() if hasattr(oldest_date, 'isoformat') else str(oldest_date)
        if newest_date:
            report.newest_file_date = newest_date.isoformat() if hasattr(newest_date, 'isoformat') else str(newest_date)

        logger.info(f"Captured metadata for {report.files_processed:,} files in {folder_count:,} folders")

    def _compute_file_hashes(self, drive_path: str, report: MetadataReport,
                             scan_id: int, show_progress: bool,
                             progress_callback: Optional[callable]) -> None:
        """Compute quick hashes for files suitable for duplicate detection"""
        if not self.db:
            return

        drive_path_obj = Path(drive_path)

        # Get files from database that need hashing
        with self.db.get_connection() as conn:
            cursor = conn.execute("""
                SELECT file_id, path, size_bytes
                FROM files
                WHERE scan_id = ? AND size_bytes >= ?
                ORDER BY size_bytes DESC
            """, (scan_id, self.min_duplicate_size))

            files_to_hash = cursor.fetchall()

        if not files_to_hash:
            logger.info("No files large enough for duplicate detection")
            return

        logger.info(f"Computing hashes for {len(files_to_hash):,} files...")

        hash_batch = []
        hashed_count = 0

        try:
            from tqdm import tqdm
            iterator = tqdm(files_to_hash, desc="Hashing", disable=not show_progress)
        except ImportError:
            iterator = files_to_hash

        for row in iterator:
            file_id = row['file_id']
            rel_path = row['path']
            file_size = row['size_bytes']

            # Build full path
            full_path = str(drive_path_obj / rel_path)

            # Compute quick hash
            quick_hash, error = compute_quick_hash(full_path)

            if quick_hash:
                hash_batch.append({
                    'scan_id': scan_id,
                    'file_id': file_id,
                    'hash_type': 'quick',
                    'hash_value': quick_hash
                })
                hashed_count += 1

                if len(hash_batch) >= self.batch_size:
                    self.db.insert_file_hashes_batch(hash_batch)
                    hash_batch = []
            else:
                if error and 'Permission' not in error:
                    logger.debug(f"Hash error for {rel_path}: {error}")

            if progress_callback and hashed_count % 1000 == 0:
                progress_callback(
                    hashed_count, len(files_to_hash),
                    f"Hashed {hashed_count:,} of {len(files_to_hash):,} files..."
                )

        # Insert remaining hashes
        if hash_batch:
            self.db.insert_file_hashes_batch(hash_batch)

        report.files_hashed = hashed_count
        logger.info(f"Computed hashes for {hashed_count:,} files")

    def _identify_duplicates(self, report: MetadataReport, scan_id: int,
                              verify_with_sha256: bool) -> None:
        """Identify duplicate groups within the scan"""
        if not self.db:
            return

        # Find files with matching quick hashes
        with self.db.get_connection() as conn:
            cursor = conn.execute("""
                SELECT
                    h.hash_value,
                    f.size_bytes,
                    COUNT(*) as count,
                    GROUP_CONCAT(f.file_id) as file_ids,
                    GROUP_CONCAT(f.path, '|||') as paths
                FROM file_hashes h
                JOIN files f ON h.file_id = f.file_id
                WHERE h.scan_id = ? AND h.hash_type = 'quick'
                GROUP BY h.hash_value, f.size_bytes
                HAVING COUNT(*) > 1
                ORDER BY f.size_bytes DESC
                LIMIT 1000
            """, (scan_id,))

            duplicate_candidates = cursor.fetchall()

        if not duplicate_candidates:
            logger.info("No duplicate files detected")
            return

        logger.info(f"Found {len(duplicate_candidates)} potential duplicate groups")

        total_wasted = 0
        groups = []

        for row in duplicate_candidates:
            hash_value = row['hash_value']
            file_size = row['size_bytes']
            count = row['count']
            file_ids = row['file_ids'].split(',')
            paths = row['paths'].split('|||')

            # Create duplicate group
            group = DuplicateGroup(
                quick_hash=hash_value,
                file_size=file_size,
                wasted_bytes=file_size * (count - 1)  # All but one are "wasted"
            )

            for i, (fid, path) in enumerate(zip(file_ids, paths)):
                member = DuplicateInfo(
                    file_id=int(fid),
                    scan_id=scan_id,
                    path=path,
                    size_bytes=file_size,
                    quick_hash=hash_value
                )
                group.members.append(member)

            # Optionally verify with SHA-256
            if verify_with_sha256 and len(group.members) > 1:
                # TODO: Implement SHA-256 verification for large groups
                pass

            total_wasted += group.wasted_bytes
            groups.append(group.to_dict())

            # Store in database
            if self.db:
                try:
                    with self.db.get_connection() as conn:
                        cursor = conn.execute("""
                            INSERT INTO duplicate_groups
                            (hash_value, file_size, file_count, total_wasted_bytes, created_at, status)
                            VALUES (?, ?, ?, ?, ?, 'unresolved')
                        """, (hash_value, file_size, count, group.wasted_bytes, datetime.now()))
                        group_id = cursor.lastrowid

                        # Insert members
                        for i, member in enumerate(group.members):
                            conn.execute("""
                                INSERT INTO duplicate_members
                                (group_id, file_id, scan_id, is_primary)
                                VALUES (?, ?, ?, ?)
                            """, (group_id, member.file_id, scan_id, i == 0))

                except Exception as e:
                    logger.warning(f"Error storing duplicate group: {e}")

        report.duplicate_groups_found = len(groups)
        report.total_duplicate_files = sum(len(g.get('members', [])) for g in groups)
        report.total_wasted_bytes = total_wasted
        report.duplicate_groups = groups[:50]  # Limit stored groups in report

        logger.info(f"Identified {len(groups)} duplicate groups, {report.total_wasted_bytes:,} bytes potentially wasted")

    def _find_cross_scan_duplicates(self, report: MetadataReport, scan_id: int) -> None:
        """Find duplicates that exist in previous scans"""
        if not self.db:
            return

        try:
            # Use the database method to find potential cross-scan duplicates
            potential_dups = self.db.find_potential_duplicates(scan_id, self.min_duplicate_size)

            if potential_dups:
                report.cross_scan_duplicates = len(potential_dups)
                report.warnings.append(
                    f"Found {len(potential_dups)} files that may duplicate files from other drives"
                )
                logger.info(f"Found {len(potential_dups)} potential cross-scan duplicates")

                # Add first few to report for review
                if potential_dups:
                    cross_scan_summary = []
                    for dup in potential_dups[:20]:
                        cross_scan_summary.append({
                            'new_file': dup['new_path'],
                            'existing_file': dup['existing_path'],
                            'existing_drive': dup['existing_drive'],
                            'size_bytes': dup['size_bytes']
                        })
                    report.duplicate_groups.append({
                        'type': 'cross_scan_candidates',
                        'count': len(potential_dups),
                        'samples': cross_scan_summary
                    })

        except Exception as e:
            logger.warning(f"Error checking cross-scan duplicates: {e}")

    def _generate_recommendations(self, report: MetadataReport) -> List[str]:
        """Generate recommendations based on capture results"""
        recommendations = []

        # Size-based recommendations
        if report.total_wasted_bytes > 1024 * 1024 * 1024:  # > 1GB
            gb_wasted = report.total_wasted_bytes / (1024 * 1024 * 1024)
            recommendations.append(f"Consider reviewing duplicates - {gb_wasted:.1f} GB potentially recoverable")

        if report.duplicate_groups_found > 100:
            recommendations.append(f"High number of duplicate groups ({report.duplicate_groups_found}) - may indicate backup copies or version control artifacts")

        # Extension-based recommendations
        if report.extension_counts:
            top_ext = sorted(report.extension_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            if '.tmp' in [ext for ext, count in top_ext]:
                recommendations.append("Many temporary files detected - consider cleanup")
            if '.bak' in [ext for ext, count in top_ext]:
                recommendations.append("Many backup files detected - review if still needed")

        # Date-based recommendations
        if report.oldest_file_date and report.newest_file_date:
            recommendations.append(f"Files span from {report.oldest_file_date[:10]} to {report.newest_file_date[:10]}")

        # Error-based recommendations
        if report.errors_count > report.files_processed * 0.1:
            recommendations.append(f"High error rate ({report.errors_count} errors) - check drive health or permissions")

        # Cross-scan duplicates
        if report.cross_scan_duplicates > 0:
            recommendations.append(f"Review {report.cross_scan_duplicates} files that may be duplicated across drives")

        if not recommendations:
            recommendations.append("Metadata capture complete - no issues identified")

        return recommendations

    def _generate_summary(self, report: MetadataReport) -> str:
        """Generate human-readable summary"""
        parts = []
        parts.append(f"Drive {report.drive_letter}:")
        parts.append(f"{report.total_files:,} files in {report.total_folders:,} folders")

        # Total size
        if report.total_size_bytes > 1024 * 1024 * 1024:
            size_gb = report.total_size_bytes / (1024 * 1024 * 1024)
            parts.append(f"({size_gb:.1f} GB)")
        else:
            size_mb = report.total_size_bytes / (1024 * 1024)
            parts.append(f"({size_mb:.1f} MB)")

        # Duplicates
        if report.duplicate_groups_found > 0:
            parts.append(f"| {report.duplicate_groups_found} duplicate groups")
            if report.total_wasted_bytes > 1024 * 1024 * 1024:
                wasted_gb = report.total_wasted_bytes / (1024 * 1024 * 1024)
                parts.append(f"({wasted_gb:.1f} GB wasted)")

        # Errors
        if report.errors_count > 0:
            parts.append(f"| {report.errors_count} errors")

        return " ".join(parts)


def run_metadata_inspection(drive_path: str, db_path: Optional[str] = None,
                            session_id: Optional[int] = None,
                            scan_id: Optional[int] = None,
                            enable_hashing: bool = True,
                            verify_sha256: bool = False,
                            show_progress: bool = True,
                            json_output: bool = False) -> Dict[str, Any]:
    """
    Convenience function to run metadata capture inspection.

    Args:
        drive_path: Path to drive
        db_path: Optional database path
        session_id: Optional inspection session ID
        scan_id: Optional scan ID to use
        enable_hashing: Enable duplicate detection
        verify_sha256: Verify duplicates with SHA-256
        show_progress: Show progress bar
        json_output: Return raw dict for JSON serialization

    Returns:
        Metadata report as dictionary
    """
    inspector = MetadataCapture(db_path)
    report = inspector.inspect(
        drive_path,
        session_id=session_id,
        scan_id=scan_id,
        enable_hashing=enable_hashing,
        verify_with_sha256=verify_sha256,
        show_progress=show_progress
    )

    return report.to_dict()


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Metadata Capture - Pass 3')
    parser.add_argument('drive_path', help='Path to drive (e.g., /mnt/d or D:)')
    parser.add_argument('--db', help='Database path for storing results')
    parser.add_argument('--session', type=int, help='Inspection session ID')
    parser.add_argument('--scan-id', type=int, help='Existing scan ID to use')
    parser.add_argument('--no-hashing', action='store_true', help='Skip duplicate detection')
    parser.add_argument('--verify-sha256', action='store_true', help='Verify duplicates with SHA-256')
    parser.add_argument('--min-size', type=int, default=1024, help='Minimum file size for duplicate detection')
    parser.add_argument('--no-progress', action='store_true', help='Disable progress bar')
    parser.add_argument('--json', action='store_true', help='Output as JSON')

    args = parser.parse_args()

    inspector = MetadataCapture(
        args.db,
        min_duplicate_size=args.min_size
    )
    report = inspector.inspect(
        args.drive_path,
        session_id=args.session,
        scan_id=args.scan_id,
        enable_hashing=not args.no_hashing,
        verify_with_sha256=args.verify_sha256,
        show_progress=not args.no_progress
    )

    if args.json:
        print(report.to_json())
    else:
        print("\n" + "=" * 60)
        print("METADATA CAPTURE REPORT")
        print("=" * 60)
        print(f"\nDrive: {report.drive_letter}: ({report.drive_path})")
        print(f"Time: {report.inspection_time}")
        print(f"Scan ID: {report.scan_id}")

        print(f"\n--- File Statistics ---")
        print(f"Total Files: {report.total_files:,}")
        print(f"Total Folders: {report.total_folders:,}")
        print(f"Total Size: {report.total_size_bytes / (1024*1024*1024):.2f} GB")
        print(f"Files Hashed: {report.files_hashed:,}")
        print(f"Files Skipped: {report.files_skipped:,}")
        print(f"Errors: {report.errors_count}")

        if report.oldest_file_date:
            print(f"\nDate Range: {report.oldest_file_date[:10]} to {report.newest_file_date[:10]}")

        if report.largest_file_path:
            print(f"\nLargest File: {report.largest_file_path}")
            print(f"  Size: {report.largest_file_size / (1024*1024):.1f} MB")

        if report.extension_counts:
            print(f"\n--- Top Extensions ---")
            sorted_exts = sorted(report.extension_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            for ext, count in sorted_exts:
                size = report.extension_sizes.get(ext, 0) / (1024 * 1024)
                print(f"  {ext}: {count:,} files ({size:.1f} MB)")

        if report.size_distribution:
            print(f"\n--- Size Distribution ---")
            for size_class, count in sorted(report.size_distribution.items()):
                print(f"  {size_class}: {count:,} files")

        print(f"\n--- Duplicate Detection ---")
        print(f"Duplicate Groups: {report.duplicate_groups_found}")
        print(f"Total Duplicate Files: {report.total_duplicate_files}")
        print(f"Potential Wasted Space: {report.total_wasted_bytes / (1024*1024):.1f} MB")
        if report.cross_scan_duplicates > 0:
            print(f"Cross-Scan Duplicates: {report.cross_scan_duplicates}")

        if report.duplicate_groups and len(report.duplicate_groups) > 0:
            print(f"\n--- Sample Duplicate Groups (top 5) ---")
            for i, group in enumerate(report.duplicate_groups[:5]):
                if group.get('type') == 'cross_scan_candidates':
                    continue
                print(f"\n  Group {i+1}: {group.get('member_count', 0)} files, {group.get('file_size', 0):,} bytes each")
                for member in group.get('members', [])[:3]:
                    print(f"    - {member.get('path', 'unknown')}")
                if group.get('member_count', 0) > 3:
                    print(f"    ... and {group.get('member_count', 0) - 3} more")

        print(f"\nSummary: {report.summary}")

        if report.errors:
            print(f"\nERRORS ({len(report.errors)}):")
            for error in report.errors[:5]:
                print(f"  - {error}")

        if report.warnings:
            print(f"\nWARNINGS ({len(report.warnings)}):")
            for warning in report.warnings:
                print(f"  - {warning}")

        if report.recommendations:
            print(f"\nRECOMMENDATIONS:")
            for rec in report.recommendations:
                print(f"  - {rec}")

        print("\n" + "=" * 60)
