#!/usr/bin/env python
"""
Safe Deduplication Script
Removes duplicate files while keeping one copy of each unique file.

Usage:
  python deduplicate.py                    # Dry-run (safe, shows what would be deleted)
  python deduplicate.py --plan             # Generate deletion plan CSV
  python deduplicate.py --execute          # Actually delete files (requires confirmation)
  python deduplicate.py --exclude Backups  # Exclude paths containing "Backups"
"""

import sys
sys.path.insert(0, 'python')

import sqlite3
import json
import csv
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import argparse

from core.logger import get_logger

logger = get_logger(__name__)

class DuplicateRemover:
    """Safe duplicate file removal with multiple safety checks."""

    def __init__(
        self,
        db_path: str = 'output/archive.db',
        dry_run: bool = True,
        exclude_patterns: List[str] = None,
        batch_size: int = 100,
        skip_confirmation: bool = False
    ):
        self.db_path = db_path
        self.dry_run = dry_run
        self.exclude_patterns = exclude_patterns or []
        self.batch_size = batch_size
        self.skip_confirmation = skip_confirmation
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

        # Statistics
        self.stats = {
            'total_groups': 0,
            'total_duplicates': 0,
            'total_kept': 0,
            'total_deleted': 0,
            'space_recovered_bytes': 0,
            'errors': 0
        }

        # Deletion log
        self.deletion_log = []

    def get_duplicate_groups(self) -> List[Dict]:
        """Get all duplicate file groups from database."""
        logger.info("Querying duplicate groups...")

        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT hash_value, COUNT(DISTINCT file_id) as count
            FROM file_hashes
            WHERE hash_type = 'quick_hash'
            GROUP BY hash_value
            HAVING COUNT(DISTINCT file_id) > 1
            ORDER BY COUNT(*) DESC
        """)

        hash_groups = cursor.fetchall()
        logger.info(f"Found {len(hash_groups):,} duplicate groups")

        groups = []
        for row in hash_groups:
            hash_value = row['hash_value']

            # Get all files with this hash
            cursor.execute("""
                SELECT
                    f.file_id,
                    f.scan_id,
                    f.path,
                    f.size_bytes,
                    f.modified_date,
                    f.created_date,
                    s.mount_point as drive_letter
                FROM files f
                JOIN file_hashes fh ON f.file_id = fh.file_id
                JOIN scans s ON f.scan_id = s.scan_id
                WHERE fh.hash_value = ? AND fh.hash_type = 'quick_hash'
                ORDER BY f.path
            """, (hash_value,))

            files = [dict(row) for row in cursor.fetchall()]

            groups.append({
                'hash': hash_value,
                'files': files,
                'count': len(files)
            })

        self.stats['total_groups'] = len(groups)
        return groups

    def should_exclude_path(self, path: str) -> bool:
        """Check if path should be excluded from deletion."""
        for pattern in self.exclude_patterns:
            if pattern.lower() in path.lower():
                return True
        return False

    def score_file_for_keeping(self, file: Dict) -> Tuple[int, str]:
        """
        Score a file for keeping (higher = more likely to keep).
        Returns (score, reason).
        """
        score = 0
        reasons = []

        path = file['path']

        # Priority 1: Avoid backup/temp/cache directories
        bad_patterns = ['backup', 'temp', '.old', 'cache', 'recycle']
        if any(pattern in path.lower() for pattern in bad_patterns):
            score -= 100
            reasons.append("in backup/temp/cache dir")
        else:
            score += 100
            reasons.append("not in backup/temp")

        # Priority 2: Prefer shorter paths (likely original location)
        path_depth = path.count('\\') + path.count('/')
        score -= path_depth * 5
        reasons.append(f"depth={path_depth}")

        # Priority 3: Prefer /shares/ over other locations
        if '/shares/' in path or '\\shares\\' in path:
            score += 50
            reasons.append("in shares")

        # Priority 4: Newer modification date (tie-breaker)
        if file['modified_date']:
            try:
                mod_date = datetime.fromisoformat(file['modified_date'].replace('T', ' '))
                days_old = (datetime.now() - mod_date).days
                score -= days_old // 365  # Slight penalty for older files
                reasons.append(f"age={days_old}d")
            except:
                pass

        return (score, ", ".join(reasons))

    def choose_keeper(self, files: List[Dict]) -> Tuple[Dict, List[Dict]]:
        """
        Choose which file to keep and which to delete.
        Returns (keeper, to_delete).
        """
        # Score all files
        scored = []
        for f in files:
            score, reason = self.score_file_for_keeping(f)
            scored.append((score, reason, f))

        # Sort by score (highest first)
        scored.sort(key=lambda x: x[0], reverse=True)

        # Keep highest scorer
        keeper = scored[0][2]
        keeper['keep_reason'] = scored[0][1]
        keeper['keep_score'] = scored[0][0]

        # Mark rest for deletion
        to_delete = []
        for score, reason, f in scored[1:]:
            if not self.should_exclude_path(f['path']):
                f['delete_reason'] = f"lower score ({score} vs {scored[0][0]})"
                to_delete.append(f)
            else:
                logger.info(f"Excluding from deletion: {f['path']}")

        return keeper, to_delete

    def generate_deletion_plan(self, output_file: str = 'output/deletion_plan.csv'):
        """Generate CSV showing what will be kept vs deleted."""
        logger.info("Generating deletion plan...")

        groups = self.get_duplicate_groups()

        Path(output_file).parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)

            writer.writerow([
                'hash',
                'action',
                'file_id',
                'path',
                'size_mb',
                'modified_date',
                'reason',
                'score'
            ])

            for group in groups:
                keeper, to_delete = self.choose_keeper(group['files'])

                # Write keeper
                writer.writerow([
                    group['hash'],
                    'KEEP',
                    keeper['file_id'],
                    keeper['path'],
                    f"{keeper['size_bytes'] / (1024*1024):.2f}",
                    keeper['modified_date'],
                    keeper['keep_reason'],
                    keeper['keep_score']
                ])

                # Write files to delete
                for f in to_delete:
                    writer.writerow([
                        group['hash'],
                        'DELETE',
                        f['file_id'],
                        f['path'],
                        f"{f['size_bytes'] / (1024*1024):.2f}",
                        f['modified_date'],
                        f.get('delete_reason', ''),
                        ''
                    ])

                    self.stats['total_duplicates'] += 1
                    self.stats['space_recovered_bytes'] += f['size_bytes']

        logger.info(f"Deletion plan saved to {output_file}")
        print(f"\nDeletion Plan Summary:")
        print(f"  Duplicate groups: {self.stats['total_groups']:,}")
        print(f"  Files to delete: {self.stats['total_duplicates']:,}")
        print(f"  Space to recover: {self.stats['space_recovered_bytes'] / (1024**3):.2f} GB")
        print(f"\nReview plan at: {output_file}")

        return output_file

    def execute_deletions(self):
        """Actually delete the duplicate files."""
        if self.dry_run:
            print("ERROR: Cannot execute deletions in dry-run mode")
            print("Use --execute flag to enable actual deletion")
            return False

        logger.warning("EXECUTING DELETIONS - Files will be permanently removed")

        groups = self.get_duplicate_groups()

        # Confirmation prompt
        print(f"\n{'='*60}")
        print(f"DELETION CONFIRMATION")
        print(f"{'='*60}")
        print(f"  Duplicate groups: {len(groups):,}")

        # Calculate totals
        total_to_delete = 0
        total_space = 0
        for group in groups:
            _, to_delete = self.choose_keeper(group['files'])
            total_to_delete += len(to_delete)
            total_space += sum(f['size_bytes'] for f in to_delete)

        print(f"  Files to delete: {total_to_delete:,}")
        print(f"  Space to recover: {total_space / (1024**3):.2f} GB")
        print(f"\nThis action CANNOT be undone!")

        if not self.skip_confirmation:
            print(f"Type 'DELETE' to proceed, or anything else to cancel: ", end='')
            confirmation = input().strip()

            if confirmation != 'DELETE':
                print("Deletion cancelled")
                return False
        else:
            print("Confirmation skipped (--yes flag provided)")

        logger.warning("User confirmed deletion - proceeding")
        print("\nDeleting files...")

        # Create deletion log file
        log_file = f"output/deletion_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        # Process in batches
        deleted_count = 0
        error_count = 0

        for i, group in enumerate(groups, 1):
            keeper, to_delete = self.choose_keeper(group['files'])

            for f in to_delete:
                try:
                    # Build full path
                    full_path = Path(f['drive_letter']) / f['path']

                    if full_path.exists():
                        full_path.unlink()
                        deleted_count += 1
                        self.stats['space_recovered_bytes'] += f['size_bytes']

                        # Log deletion
                        self.deletion_log.append({
                            'file_id': f['file_id'],
                            'path': str(full_path),
                            'hash': group['hash'],
                            'size_bytes': f['size_bytes'],
                            'deleted_at': datetime.now().isoformat(),
                            'keeper': keeper['path']
                        })

                        logger.info(f"Deleted: {full_path}")
                    else:
                        logger.warning(f"File not found (skipped): {full_path}")
                        error_count += 1

                except Exception as e:
                    logger.error(f"Failed to delete {f['path']}: {e}", exc_info=True)
                    error_count += 1

            # Progress update
            if i % 100 == 0:
                print(f"  Processed {i:,} / {len(groups):,} groups ({deleted_count:,} files deleted)")

        # Save deletion log
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'stats': {
                    'groups_processed': len(groups),
                    'files_deleted': deleted_count,
                    'errors': error_count,
                    'space_recovered_gb': self.stats['space_recovered_bytes'] / (1024**3)
                },
                'deletions': self.deletion_log
            }, f, indent=2)

        print(f"\nDeletion Complete!")
        print(f"  Files deleted: {deleted_count:,}")
        print(f"  Errors: {error_count:,}")
        print(f"  Space recovered: {self.stats['space_recovered_bytes'] / (1024**3):.2f} GB")
        print(f"  Log saved to: {log_file}")

        return True

def main():
    parser = argparse.ArgumentParser(
        description='Safe duplicate file removal',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        '--plan',
        action='store_true',
        help='Generate deletion plan CSV (safe, no files deleted)'
    )

    parser.add_argument(
        '--execute',
        action='store_true',
        help='Actually delete files (DANGEROUS - requires confirmation)'
    )

    parser.add_argument(
        '--yes',
        action='store_true',
        help='Skip confirmation prompt (use with --execute)'
    )

    parser.add_argument(
        '--exclude',
        action='append',
        default=[],
        help='Exclude paths containing this pattern (can specify multiple times)'
    )

    parser.add_argument(
        '--batch-size',
        type=int,
        default=100,
        help='Process files in batches of this size (default: 100)'
    )

    args = parser.parse_args()

    # Default to plan mode if no action specified
    if not args.plan and not args.execute:
        args.plan = True
        print("No action specified, defaulting to --plan (safe mode)")
        print("Use --execute to actually delete files\n")

    remover = DuplicateRemover(
        dry_run=not args.execute,
        exclude_patterns=args.exclude,
        batch_size=args.batch_size,
        skip_confirmation=args.yes
    )

    if args.plan:
        remover.generate_deletion_plan()
    elif args.execute:
        # Generate plan first with timestamped filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        plan_file = remover.generate_deletion_plan(f'output/deletion_plan_{timestamp}.csv')
        print(f"\nReview the deletion plan above before proceeding.")
        print(f"Plan saved to: {plan_file}\n")

        # Then execute
        remover.execute_deletions()

if __name__ == '__main__':
    main()
