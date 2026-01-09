"""
Pass 4: Interactive Review

Compiles results from all previous passes (health, OS, metadata) and presents
decision points for user/Claude review. Generates Claude-friendly markdown
reports for each inspection session.

Decision Points:
- Duplicate handling (skip all, catalog with flag, review individually)
- OS preservation (mark as bootable archive, treat as data-only)
- File filtering (skip certain folders, include/exclude patterns)
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.logger import get_logger
from core.database import Database

logger = get_logger(__name__)


class DuplicateHandling(str, Enum):
    """Options for handling duplicate files"""
    SKIP_ALL = "skip_all"
    CATALOG_WITH_FLAG = "catalog_with_flag"
    REVIEW_INDIVIDUALLY = "review_individually"


class OSPreservation(str, Enum):
    """Options for handling bootable OS installations"""
    BOOTABLE_ARCHIVE = "bootable_archive"
    DATA_ONLY = "data_only"


class FilterAction(str, Enum):
    """Options for folder/file filtering"""
    INCLUDE = "include"
    EXCLUDE = "exclude"
    SKIP = "skip"


@dataclass
class DecisionPoint:
    """A decision point requiring user/Claude input"""
    decision_id: str
    category: str  # 'duplicate', 'os', 'filter', 'custom'
    title: str
    description: str
    options: List[Dict[str, str]]  # [{id, label, description}]
    default_option: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    resolved: bool = False
    resolution: Optional[str] = None
    resolution_notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'decision_id': self.decision_id,
            'category': self.category,
            'title': self.title,
            'description': self.description,
            'options': self.options,
            'default_option': self.default_option,
            'context': self.context,
            'resolved': self.resolved,
            'resolution': self.resolution,
            'resolution_notes': self.resolution_notes
        }


@dataclass
class ReviewReport:
    """Complete review report for a drive inspection"""
    session_id: Optional[int] = None
    drive_path: str = ""
    drive_letter: str = ""
    drive_model: str = "Unknown"
    drive_serial: str = "Unknown"
    inspection_time: str = ""

    # Summary from previous passes
    health_summary: Dict[str, Any] = field(default_factory=dict)
    os_summary: Dict[str, Any] = field(default_factory=dict)
    metadata_summary: Dict[str, Any] = field(default_factory=dict)

    # Decision points
    decision_points: List[Dict[str, Any]] = field(default_factory=list)
    resolved_decisions: List[Dict[str, Any]] = field(default_factory=list)

    # Recommendations
    recommendations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    # Report metadata
    report_path: Optional[str] = None
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'session_id': self.session_id,
            'drive_path': self.drive_path,
            'drive_letter': self.drive_letter,
            'drive_model': self.drive_model,
            'drive_serial': self.drive_serial,
            'inspection_time': self.inspection_time,
            'health_summary': self.health_summary,
            'os_summary': self.os_summary,
            'metadata_summary': self.metadata_summary,
            'decision_points': self.decision_points,
            'resolved_decisions': self.resolved_decisions,
            'recommendations': self.recommendations,
            'warnings': self.warnings,
            'errors': self.errors,
            'report_path': self.report_path,
            'summary': self.summary
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), indent=indent, default=str)


class InteractiveReview:
    """
    Interactive review for Pass 4 of the multi-pass inspection workflow.

    Compiles results from passes 1-3 and presents decision points:
    1. Compile health, OS, and metadata reports
    2. Generate decision points based on findings
    3. Present options for user/Claude review
    4. Record decisions in database
    5. Generate Claude-friendly markdown report

    Generates a markdown report suitable for Claude analysis and user review.
    """

    def __init__(self, db_path: Optional[str] = None,
                 reports_dir: str = "output/reports"):
        """
        Initialize the interactive review inspector.

        Args:
            db_path: Path to SQLite database for storing results
            reports_dir: Directory for saving markdown reports
        """
        self.db = Database(db_path) if db_path else None
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"InteractiveReview initialized (reports_dir={reports_dir})")

    def _extract_drive_letter(self, drive_path: str) -> Optional[str]:
        """Extract Windows drive letter from path"""
        import re
        if len(drive_path) >= 1 and drive_path[1:2] == ':':
            return drive_path[0].upper()
        match = re.match(r'^/mnt/([a-zA-Z])(?:/|$)', drive_path)
        if match:
            return match.group(1).upper()
        return None

    def _load_pass_report(self, session_id: int, pass_number: int) -> Optional[Dict[str, Any]]:
        """Load a completed pass report from the database"""
        if not self.db:
            return None

        with self.db.get_connection() as conn:
            cursor = conn.execute("""
                SELECT report_json, status, error_message
                FROM inspection_passes
                WHERE session_id = ? AND pass_number = ?
            """, (session_id, pass_number))
            row = cursor.fetchone()

            if row and row['report_json']:
                try:
                    return json.loads(row['report_json'])
                except json.JSONDecodeError:
                    logger.warning(f"Could not parse report JSON for pass {pass_number}")
            return None

    def _compile_health_summary(self, health_report: Optional[Dict]) -> Dict[str, Any]:
        """Compile health summary from Pass 1 report"""
        if not health_report:
            return {'status': 'not_available', 'message': 'Health inspection not completed'}

        return {
            'status': health_report.get('overall_health', 'Unknown'),
            'score': health_report.get('health_score', 0),
            'errors': health_report.get('errors', []),
            'warnings': health_report.get('warnings', []),
            'recommendations': health_report.get('recommendations', []),
            'chkdsk_success': health_report.get('chkdsk_result', {}).get('success', False),
            'smart_available': health_report.get('smart_data', {}).get('available', False)
        }

    def _compile_os_summary(self, os_report: Optional[Dict]) -> Dict[str, Any]:
        """Compile OS summary from Pass 2 report"""
        if not os_report:
            return {'status': 'not_available', 'message': 'OS detection not completed'}

        return {
            'os_type': os_report.get('os_type', 'Unknown'),
            'os_name': os_report.get('os_name', 'Unknown'),
            'version': os_report.get('version'),
            'build_number': os_report.get('build_number'),
            'edition': os_report.get('edition'),
            'boot_capable': os_report.get('boot_capable', False),
            'confidence': os_report.get('confidence', 'Unknown'),
            'detection_method': os_report.get('detection_method', 'None'),
            'user_profiles': os_report.get('user_profiles', []),
            'windows_features': os_report.get('windows_features', {})
        }

    def _compile_metadata_summary(self, metadata_report: Optional[Dict]) -> Dict[str, Any]:
        """Compile metadata summary from Pass 3 report"""
        if not metadata_report:
            return {'status': 'not_available', 'message': 'Metadata capture not completed'}

        return {
            'total_files': metadata_report.get('total_files', 0),
            'total_folders': metadata_report.get('total_folders', 0),
            'total_size_bytes': metadata_report.get('total_size_bytes', 0),
            'files_hashed': metadata_report.get('files_hashed', 0),
            'duplicate_groups': metadata_report.get('duplicate_groups_found', 0),
            'total_duplicate_files': metadata_report.get('total_duplicate_files', 0),
            'wasted_bytes': metadata_report.get('total_wasted_bytes', 0),
            'cross_scan_duplicates': metadata_report.get('cross_scan_duplicates', 0),
            'oldest_file': metadata_report.get('oldest_file_date'),
            'newest_file': metadata_report.get('newest_file_date'),
            'top_extensions': self._get_top_extensions(metadata_report.get('extension_counts', {}))
        }

    def _get_top_extensions(self, extension_counts: Dict[str, int], limit: int = 5) -> List[Dict]:
        """Get top N extensions by count"""
        sorted_exts = sorted(extension_counts.items(), key=lambda x: x[1], reverse=True)
        return [{'extension': ext, 'count': count} for ext, count in sorted_exts[:limit]]

    def _generate_decision_points(self, report: ReviewReport) -> List[DecisionPoint]:
        """Generate decision points based on inspection findings"""
        decisions = []

        # Decision 1: Duplicate Handling
        dup_count = report.metadata_summary.get('duplicate_groups', 0)
        cross_dup_count = report.metadata_summary.get('cross_scan_duplicates', 0)
        wasted_bytes = report.metadata_summary.get('wasted_bytes', 0)

        if dup_count > 0 or cross_dup_count > 0:
            wasted_mb = wasted_bytes / (1024 * 1024)
            decisions.append(DecisionPoint(
                decision_id='duplicate_handling',
                category='duplicate',
                title='Duplicate Handling',
                description=f'Found {dup_count} duplicate groups ({cross_dup_count} cross-scan). '
                           f'Approximately {wasted_mb:.1f} MB potentially recoverable.',
                options=[
                    {
                        'id': DuplicateHandling.SKIP_ALL.value,
                        'label': 'Skip all duplicates',
                        'description': 'Do not catalog files already archived from other drives'
                    },
                    {
                        'id': DuplicateHandling.CATALOG_WITH_FLAG.value,
                        'label': 'Catalog with flag',
                        'description': 'Catalog all files but mark duplicates for later review'
                    },
                    {
                        'id': DuplicateHandling.REVIEW_INDIVIDUALLY.value,
                        'label': 'Review individually',
                        'description': 'Present each duplicate group for individual decision'
                    }
                ],
                default_option=DuplicateHandling.CATALOG_WITH_FLAG.value,
                context={
                    'duplicate_groups': dup_count,
                    'cross_scan_duplicates': cross_dup_count,
                    'wasted_bytes': wasted_bytes
                }
            ))

        # Decision 2: OS Preservation
        os_type = report.os_summary.get('os_type')
        boot_capable = report.os_summary.get('boot_capable', False)

        if os_type == 'Windows' and boot_capable:
            os_name = report.os_summary.get('os_name', 'Unknown')
            version = report.os_summary.get('version', '')
            decisions.append(DecisionPoint(
                decision_id='os_preservation',
                category='os',
                title='OS Preservation',
                description=f'Valid bootable {os_name} {version} installation detected.',
                options=[
                    {
                        'id': OSPreservation.BOOTABLE_ARCHIVE.value,
                        'label': 'Mark as bootable archive',
                        'description': 'Preserve as a complete system image that could be restored'
                    },
                    {
                        'id': OSPreservation.DATA_ONLY.value,
                        'label': 'Treat as data-only',
                        'description': 'Archive user data only, ignore system files'
                    }
                ],
                default_option=OSPreservation.DATA_ONLY.value,
                context={
                    'os_name': os_name,
                    'version': version,
                    'edition': report.os_summary.get('edition'),
                    'user_profiles': report.os_summary.get('user_profiles', [])
                }
            ))

        # Decision 3: System Folder Filtering
        if os_type == 'Windows':
            decisions.append(DecisionPoint(
                decision_id='system_folder_filter',
                category='filter',
                title='System Folder Filtering',
                description='Choose which Windows system folders to include in the archive.',
                options=[
                    {
                        'id': 'exclude_windows',
                        'label': 'Exclude Windows folder',
                        'description': 'Skip C:\\Windows and system files'
                    },
                    {
                        'id': 'exclude_all_system',
                        'label': 'Exclude all system folders',
                        'description': 'Skip Windows, Program Files, ProgramData'
                    },
                    {
                        'id': 'include_all',
                        'label': 'Include everything',
                        'description': 'Archive all folders including system files'
                    }
                ],
                default_option='exclude_windows',
                context={
                    'estimated_system_size': 'varies'
                }
            ))

        # Decision 4: Health-based action (if issues found)
        health_score = report.health_summary.get('score', 100)
        if health_score < 70:
            decisions.append(DecisionPoint(
                decision_id='health_action',
                category='custom',
                title='Health Warning Action',
                description=f'Drive health score is {health_score}/100. Potential issues detected.',
                options=[
                    {
                        'id': 'proceed_with_caution',
                        'label': 'Proceed with caution',
                        'description': 'Continue archiving but prioritize this drive'
                    },
                    {
                        'id': 'quick_backup_first',
                        'label': 'Quick backup first',
                        'description': 'Perform quick backup of critical files before full archive'
                    },
                    {
                        'id': 'abort_inspection',
                        'label': 'Abort inspection',
                        'description': 'Stop inspection and address health issues first'
                    }
                ],
                default_option='proceed_with_caution',
                context={
                    'health_score': health_score,
                    'errors': report.health_summary.get('errors', []),
                    'warnings': report.health_summary.get('warnings', [])
                }
            ))

        return decisions

    def _generate_recommendations(self, report: ReviewReport) -> List[str]:
        """Generate recommendations based on all inspection findings"""
        recommendations = []

        # Health-based recommendations
        health_status = report.health_summary.get('status', 'Unknown')
        if health_status in ['Critical', 'Poor']:
            recommendations.append(
                f"PRIORITY: Drive health is {health_status} - complete archiving as soon as possible"
            )

        # Duplicate-based recommendations
        wasted_bytes = report.metadata_summary.get('wasted_bytes', 0)
        if wasted_bytes > 1024 * 1024 * 1024:  # > 1GB
            wasted_gb = wasted_bytes / (1024 * 1024 * 1024)
            recommendations.append(
                f"Consider duplicate cleanup - {wasted_gb:.1f} GB potentially recoverable"
            )

        # OS-based recommendations
        boot_capable = report.os_summary.get('boot_capable', False)
        if boot_capable:
            os_name = report.os_summary.get('os_name', 'Unknown OS')
            recommendations.append(
                f"Bootable {os_name} detected - consider full system backup if recovery might be needed"
            )

        # Profile-based recommendations
        user_profiles = report.os_summary.get('user_profiles', [])
        if len(user_profiles) > 3:
            recommendations.append(
                f"Multiple user profiles ({len(user_profiles)}) - review for active vs dormant accounts"
            )

        # File age recommendations
        oldest = report.metadata_summary.get('oldest_file')
        if oldest:
            recommendations.append(
                f"Files date back to {oldest[:10]} - historical data may have archival value"
            )

        if not recommendations:
            recommendations.append("No special considerations - standard archiving recommended")

        return recommendations

    def _generate_summary(self, report: ReviewReport) -> str:
        """Generate human-readable summary"""
        parts = [f"Drive {report.drive_letter}:"]

        # Health
        health_status = report.health_summary.get('status', 'Unknown')
        parts.append(f"Health: {health_status}")

        # OS
        os_name = report.os_summary.get('os_name', 'Unknown')
        if os_name != 'Unknown':
            version = report.os_summary.get('version', '')
            if version:
                parts.append(f"OS: {os_name} {version}")
            else:
                parts.append(f"OS: {os_name}")

        # Files
        total_files = report.metadata_summary.get('total_files', 0)
        total_size = report.metadata_summary.get('total_size_bytes', 0)
        if total_files > 0:
            size_gb = total_size / (1024 * 1024 * 1024)
            parts.append(f"Files: {total_files:,} ({size_gb:.1f} GB)")

        # Decision points
        pending = len([d for d in report.decision_points if not d.get('resolved', False)])
        if pending > 0:
            parts.append(f"Decisions pending: {pending}")

        return " | ".join(parts)

    def inspect(self, drive_path: str, session_id: Optional[int] = None,
                auto_resolve: bool = False,
                generate_report: bool = True) -> ReviewReport:
        """
        Perform interactive review inspection on a drive.

        Args:
            drive_path: Path to the drive (e.g., '/mnt/d', 'D:')
            session_id: Inspection session ID (required for database operations)
            auto_resolve: Automatically resolve decisions with defaults
            generate_report: Generate markdown report file

        Returns:
            ReviewReport with complete review results
        """
        report = ReviewReport()
        report.drive_path = drive_path
        report.drive_letter = self._extract_drive_letter(drive_path) or "?"
        report.inspection_time = datetime.now().isoformat()
        report.session_id = session_id

        logger.info(f"Starting interactive review for drive {report.drive_letter}: ({drive_path})")

        # Mark pass as started in database
        if self.db and session_id:
            self.db.start_pass(session_id, 4)

            # Get drive info from session
            inspection = self.db.get_inspection(session_id)
            if inspection:
                report.drive_model = inspection.get('model') or 'Unknown'
                report.drive_serial = inspection.get('serial_number') or 'Unknown'

        # Step 1: Load and compile results from passes 1-3
        logger.info("Compiling results from previous passes...")

        health_report = self._load_pass_report(session_id, 1) if session_id else None
        os_report = self._load_pass_report(session_id, 2) if session_id else None
        metadata_report = self._load_pass_report(session_id, 3) if session_id else None

        report.health_summary = self._compile_health_summary(health_report)
        report.os_summary = self._compile_os_summary(os_report)
        report.metadata_summary = self._compile_metadata_summary(metadata_report)

        # Step 2: Generate decision points
        logger.info("Generating decision points...")
        decisions = self._generate_decision_points(report)

        # Auto-resolve if requested
        if auto_resolve:
            for decision in decisions:
                if decision.default_option:
                    decision.resolved = True
                    decision.resolution = decision.default_option
                    decision.resolution_notes = "Auto-resolved with default"

        report.decision_points = [d.to_dict() for d in decisions]

        # Step 3: Load any previously recorded decisions
        if self.db and session_id:
            existing_decisions = self.db.get_decisions(session_id)
            for existing in existing_decisions:
                report.resolved_decisions.append({
                    'decision_type': existing.get('decision_type'),
                    'decision_key': existing.get('decision_key'),
                    'decision_value': existing.get('decision_value'),
                    'description': existing.get('description'),
                    'decided_at': existing.get('decided_at'),
                    'decided_by': existing.get('decided_by')
                })

        # Step 4: Generate recommendations
        report.recommendations = self._generate_recommendations(report)

        # Step 5: Generate summary
        report.summary = self._generate_summary(report)

        # Step 6: Generate markdown report
        if generate_report:
            from reports.inspection_report import InspectionReportGenerator
            try:
                generator = InspectionReportGenerator(str(self.reports_dir))
                report_path = generator.generate(report)
                report.report_path = report_path
                logger.info(f"Generated report: {report_path}")
            except Exception as e:
                report.warnings.append(f"Could not generate markdown report: {e}")
                logger.warning(f"Report generation failed: {e}")

        # Store pass results in database
        if self.db and session_id:
            try:
                self.db.complete_pass(
                    session_id, 4,
                    report_json=report.to_json(),
                    error_message='; '.join(report.errors) if report.errors else None
                )
                logger.info(f"Interactive review results saved to database (session {session_id})")
            except Exception as e:
                logger.error(f"Failed to save results to database: {e}")

        logger.info(f"Interactive review complete: {len(report.decision_points)} decision points")
        return report

    def resolve_decision(self, session_id: int, decision_id: str,
                         resolution: str, notes: Optional[str] = None,
                         decided_by: str = 'user') -> bool:
        """
        Record a decision resolution.

        Args:
            session_id: Inspection session ID
            decision_id: The decision to resolve (e.g., 'duplicate_handling')
            resolution: The chosen option ID
            notes: Optional notes about the decision
            decided_by: Who made the decision ('user' or 'claude')

        Returns:
            True if successful
        """
        if not self.db:
            logger.warning("No database connection - decision not recorded")
            return False

        try:
            self.db.record_decision(
                session_id=session_id,
                decision_type=decision_id,
                decision_key=decision_id,
                decision_value=resolution,
                description=notes,
                decided_by=decided_by
            )
            logger.info(f"Recorded decision: {decision_id} = {resolution}")
            return True
        except Exception as e:
            logger.error(f"Failed to record decision: {e}")
            return False

    def get_pending_decisions(self, session_id: int) -> List[Dict]:
        """Get decision points that haven't been resolved yet"""
        if not self.db:
            return []

        # Get all decisions for the session
        existing_decisions = self.db.get_decisions(session_id)
        resolved_ids = {d['decision_key'] for d in existing_decisions}

        # Reload the inspection to get all decision points
        inspection = self.db.get_inspection(session_id)
        if not inspection:
            return []

        # Get pass 4 report
        pass4_report = self._load_pass_report(session_id, 4)
        if not pass4_report:
            return []

        # Filter to unresolved
        all_decisions = pass4_report.get('decision_points', [])
        pending = [d for d in all_decisions if d.get('decision_id') not in resolved_ids]

        return pending


def run_review_inspection(drive_path: str, db_path: Optional[str] = None,
                          session_id: Optional[int] = None,
                          auto_resolve: bool = False,
                          generate_report: bool = True,
                          json_output: bool = False) -> Dict[str, Any]:
    """
    Convenience function to run interactive review inspection.

    Args:
        drive_path: Path to drive
        db_path: Optional database path
        session_id: Inspection session ID
        auto_resolve: Automatically resolve with defaults
        generate_report: Generate markdown report
        json_output: Return raw dict for JSON serialization

    Returns:
        Review report as dictionary
    """
    inspector = InteractiveReview(db_path)
    report = inspector.inspect(
        drive_path,
        session_id=session_id,
        auto_resolve=auto_resolve,
        generate_report=generate_report
    )

    return report.to_dict()


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Interactive Review - Pass 4')
    parser.add_argument('drive_path', help='Path to drive (e.g., /mnt/d or D:)')
    parser.add_argument('--db', help='Database path for storing results')
    parser.add_argument('--session', type=int, help='Inspection session ID', required=True)
    parser.add_argument('--auto-resolve', action='store_true', help='Auto-resolve with defaults')
    parser.add_argument('--no-report', action='store_true', help='Skip markdown report generation')
    parser.add_argument('--json', action='store_true', help='Output as JSON')

    args = parser.parse_args()

    inspector = InteractiveReview(args.db)
    report = inspector.inspect(
        args.drive_path,
        session_id=args.session,
        auto_resolve=args.auto_resolve,
        generate_report=not args.no_report
    )

    if args.json:
        print(report.to_json())
    else:
        print("\n" + "=" * 60)
        print("INTERACTIVE REVIEW REPORT")
        print("=" * 60)
        print(f"\nDrive: {report.drive_letter}: ({report.drive_path})")
        print(f"Model: {report.drive_model}")
        print(f"Serial: {report.drive_serial}")
        print(f"Time: {report.inspection_time}")

        print(f"\n--- Health Summary ---")
        health = report.health_summary
        print(f"Status: {health.get('status', 'Unknown')}")
        print(f"Score: {health.get('score', 'N/A')}/100")

        print(f"\n--- OS Summary ---")
        os_info = report.os_summary
        print(f"OS: {os_info.get('os_name', 'Unknown')}")
        print(f"Boot Capable: {os_info.get('boot_capable', False)}")
        print(f"Confidence: {os_info.get('confidence', 'Unknown')}")

        print(f"\n--- Metadata Summary ---")
        meta = report.metadata_summary
        print(f"Total Files: {meta.get('total_files', 0):,}")
        size_gb = meta.get('total_size_bytes', 0) / (1024*1024*1024)
        print(f"Total Size: {size_gb:.1f} GB")
        print(f"Duplicate Groups: {meta.get('duplicate_groups', 0)}")

        print(f"\n--- Decision Points ({len(report.decision_points)}) ---")
        for dp in report.decision_points:
            resolved = "RESOLVED" if dp.get('resolved') else "PENDING"
            print(f"\n  [{resolved}] {dp.get('title')}")
            print(f"  {dp.get('description')}")
            if dp.get('resolved'):
                print(f"  Resolution: {dp.get('resolution')}")
            else:
                print("  Options:")
                for opt in dp.get('options', []):
                    default = " (default)" if opt['id'] == dp.get('default_option') else ""
                    print(f"    - {opt['id']}: {opt['label']}{default}")

        if report.report_path:
            print(f"\n--- Report Generated ---")
            print(f"Path: {report.report_path}")

        print(f"\nSummary: {report.summary}")

        if report.recommendations:
            print(f"\nRECOMMENDATIONS:")
            for rec in report.recommendations:
                print(f"  - {rec}")

        if report.warnings:
            print(f"\nWARNINGS:")
            for warning in report.warnings:
                print(f"  - {warning}")

        print("\n" + "=" * 60)
