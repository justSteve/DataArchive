"""
Pass 2: Enhanced OS Detection Inspector

Performs registry-based operating system detection for drives:
- Reads Windows Registry offline from mounted drives
- Extracts ProductName, DisplayVersion, CurrentBuild, EditionID, InstallDate
- Falls back to pattern-based detection if registry unavailable
- Works from both Windows native and WSL environments
- Generates JSON report suitable for Claude analysis
"""

import os
import json
import platform
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.logger import get_logger
from core.database import Database
from core.os_detector import OSDetector, OSDetectionResult

logger = get_logger(__name__)


@dataclass
class OSReport:
    """Complete OS detection report for a drive"""
    drive_path: str = ""
    drive_letter: str = ""
    inspection_time: str = ""

    # Primary detection results
    os_type: str = "Unknown"
    os_name: str = "Unknown"
    version: Optional[str] = None
    build_number: Optional[str] = None
    edition: Optional[str] = None
    install_date: Optional[str] = None
    boot_capable: bool = False

    # Detection metadata
    detection_method: str = "NONE"
    confidence: str = "UNKNOWN"
    methods_tried: List[str] = field(default_factory=list)

    # Additional analysis
    windows_features: Dict[str, bool] = field(default_factory=dict)
    user_profiles: List[str] = field(default_factory=list)
    installed_programs_count: Optional[int] = None

    # Raw data for debugging
    raw_data: Dict[str, Any] = field(default_factory=dict)

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
            'os_type': self.os_type,
            'os_name': self.os_name,
            'version': self.version,
            'build_number': self.build_number,
            'edition': self.edition,
            'install_date': self.install_date,
            'boot_capable': self.boot_capable,
            'detection_method': self.detection_method,
            'confidence': self.confidence,
            'methods_tried': self.methods_tried,
            'windows_features': self.windows_features,
            'user_profiles': self.user_profiles,
            'installed_programs_count': self.installed_programs_count,
            'raw_data': self.raw_data,
            'errors': self.errors,
            'warnings': self.warnings,
            'recommendations': self.recommendations,
            'summary': self.summary
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), indent=indent, default=str)


class EnhancedOSDetector:
    """
    Enhanced OS detection for Pass 2 of the multi-pass inspection workflow.

    Performs comprehensive OS detection:
    1. Registry-based detection (HIGH confidence)
    2. Pattern-based fallback (MEDIUM/LOW confidence)
    3. Additional analysis (user profiles, features, programs)

    Generates a JSON report suitable for Claude analysis.
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize the enhanced OS detector.

        Args:
            db_path: Path to SQLite database for storing results
        """
        self.is_wsl = self._detect_wsl()
        self.is_windows = platform.system() == 'Windows'
        self.db = Database(db_path) if db_path else None
        logger.info(f"EnhancedOSDetector initialized (WSL: {self.is_wsl}, Windows: {self.is_windows})")

    def _detect_wsl(self) -> bool:
        """Detect if running in WSL"""
        try:
            if platform.system() == 'Linux':
                with open('/proc/version', 'r') as f:
                    version_info = f.read().lower()
                    return 'microsoft' in version_info or 'wsl' in version_info
        except Exception:
            pass
        return False

    def _extract_drive_letter(self, drive_path: str) -> Optional[str]:
        """Extract Windows drive letter from path"""
        import re
        if len(drive_path) >= 1 and drive_path[1:2] == ':':
            return drive_path[0].upper()
        match = re.match(r'^/mnt/([a-zA-Z])(?:/|$)', drive_path)
        if match:
            return match.group(1).upper()
        return None

    def inspect(self, drive_path: str, session_id: Optional[int] = None,
                include_extra_analysis: bool = True) -> OSReport:
        """
        Perform complete OS detection inspection on a drive.

        Args:
            drive_path: Path to the drive (e.g., '/mnt/d', 'D:')
            session_id: Optional inspection session ID for database recording
            include_extra_analysis: Include user profiles, features, etc.

        Returns:
            OSReport with complete detection results
        """
        report = OSReport()
        report.drive_path = drive_path
        report.drive_letter = self._extract_drive_letter(drive_path) or "?"
        report.inspection_time = datetime.now().isoformat()

        logger.info(f"Starting OS detection inspection of drive {report.drive_letter}: ({drive_path})")

        # Mark pass as started in database
        if self.db and session_id:
            self.db.start_pass(session_id, 2)

        # Step 1: Run primary OS detection
        logger.info("Running enhanced OS detection...")
        try:
            detector = OSDetector(drive_path)
            detection_result = detector.detect()

            # Transfer detection results to report
            report.os_type = detection_result.os_type
            report.os_name = detection_result.os_name
            report.version = detection_result.version
            report.build_number = detection_result.build_number
            report.edition = detection_result.edition
            report.install_date = detection_result.install_date
            report.boot_capable = detection_result.boot_capable
            report.detection_method = detection_result.detection_method
            report.confidence = detection_result.confidence
            report.methods_tried = detection_result.methods_tried
            report.raw_data = detection_result.raw_data
            report.errors.extend(detection_result.errors)

            logger.info(f"OS detected: {report.os_name} ({report.confidence} confidence)")

        except Exception as e:
            error_msg = f"OS detection failed: {str(e)}"
            report.errors.append(error_msg)
            logger.error(error_msg)

        # Step 2: Additional analysis for Windows drives
        if include_extra_analysis and report.os_type == 'Windows':
            self._analyze_windows_features(drive_path, report)
            self._analyze_user_profiles(drive_path, report)
            self._count_installed_programs(drive_path, report)

        # Step 3: Generate recommendations
        report.recommendations.extend(self._generate_recommendations(report))

        # Step 4: Generate summary
        report.summary = self._generate_summary(report)

        # Store in database
        if self.db and session_id:
            try:
                self.db.complete_pass(
                    session_id, 2,
                    report_json=report.to_json(),
                    error_message='; '.join(report.errors) if report.errors else None
                )
                logger.info(f"OS detection results saved to database (session {session_id})")
            except Exception as e:
                logger.error(f"Failed to save results to database: {e}")

        # Also store in os_info table if we have a scan_id
        if self.db and session_id:
            try:
                # Get or create scan_id from session
                inspection = self.db.get_inspection(session_id)
                if inspection and inspection.get('drive_id'):
                    self.db.insert_os_info(session_id, report.to_dict())
            except Exception as e:
                logger.debug(f"Could not store OS info in legacy table: {e}")

        logger.info(f"OS detection complete: {report.os_name} (confidence: {report.confidence})")
        return report

    def _analyze_windows_features(self, drive_path: str, report: OSReport) -> None:
        """Analyze Windows features present on the drive"""
        logger.debug("Analyzing Windows features...")
        path = Path(drive_path)

        features = {
            'has_wsl': (path / 'Windows' / 'System32' / 'lxss').exists(),
            'has_hyper_v': (path / 'Windows' / 'System32' / 'vmms.exe').exists(),
            'has_windows_defender': (path / 'Program Files' / 'Windows Defender').exists(),
            'has_bitlocker': (path / 'Windows' / 'System32' / 'fvenotify.exe').exists(),
            'has_powershell_7': (path / 'Program Files' / 'PowerShell' / '7').exists(),
            'has_dotnet_core': (path / 'Program Files' / 'dotnet').exists(),
            'has_visual_studio': any([
                (path / 'Program Files' / 'Microsoft Visual Studio').exists(),
                (path / 'Program Files (x86)' / 'Microsoft Visual Studio').exists()
            ]),
            'has_office': any([
                (path / 'Program Files' / 'Microsoft Office').exists(),
                (path / 'Program Files (x86)' / 'Microsoft Office').exists()
            ]),
            'has_store_apps': (path / 'Program Files' / 'WindowsApps').exists(),
            'is_64bit': (path / 'Program Files (x86)').exists(),
        }

        report.windows_features = features

        # Add relevant info to methods_tried
        if features['is_64bit']:
            report.methods_tried.append('64bit_detected')
        if features['has_wsl']:
            report.methods_tried.append('wsl_installed')

    def _analyze_user_profiles(self, drive_path: str, report: OSReport) -> None:
        """Find user profiles on the drive"""
        logger.debug("Analyzing user profiles...")
        path = Path(drive_path)

        users_path = path / 'Users'
        if users_path.exists():
            try:
                # Filter out system folders
                system_folders = {'Default', 'Default User', 'Public', 'All Users'}
                profiles = []

                for item in users_path.iterdir():
                    if item.is_dir() and item.name not in system_folders:
                        # Check for NTUSER.DAT to confirm it's a user profile
                        if (item / 'NTUSER.DAT').exists():
                            profiles.append(item.name)

                report.user_profiles = profiles
                logger.debug(f"Found {len(profiles)} user profiles")

            except PermissionError:
                report.warnings.append("Could not enumerate all user profiles (permission denied)")
            except Exception as e:
                report.warnings.append(f"Error enumerating user profiles: {e}")

        # Check legacy location for XP
        docs_settings = path / 'Documents and Settings'
        if docs_settings.exists() and not users_path.exists():
            try:
                system_folders = {'Default User', 'All Users', 'NetworkService', 'LocalService'}
                profiles = []

                for item in docs_settings.iterdir():
                    if item.is_dir() and item.name not in system_folders:
                        if (item / 'NTUSER.DAT').exists():
                            profiles.append(item.name)

                report.user_profiles = profiles

            except Exception as e:
                report.warnings.append(f"Error enumerating legacy user profiles: {e}")

    def _count_installed_programs(self, drive_path: str, report: OSReport) -> None:
        """Count installed programs on the drive"""
        logger.debug("Counting installed programs...")
        path = Path(drive_path)

        count = 0

        # Check Program Files
        for pf_path in [path / 'Program Files', path / 'Program Files (x86)']:
            if pf_path.exists():
                try:
                    count += sum(1 for item in pf_path.iterdir() if item.is_dir())
                except PermissionError:
                    pass
                except Exception:
                    pass

        report.installed_programs_count = count
        logger.debug(f"Found approximately {count} installed programs")

    def _generate_recommendations(self, report: OSReport) -> List[str]:
        """Generate recommendations based on OS detection results"""
        recommendations = []

        if report.confidence == 'UNKNOWN':
            recommendations.append("Could not detect OS - drive may not be bootable or may use unsupported filesystem")

        if report.confidence == 'LOW':
            recommendations.append("Low confidence OS detection - verify manually before relying on results")

        if report.os_type == 'Windows':
            # Windows-specific recommendations
            if report.edition and 'Server' in report.edition:
                recommendations.append("Server OS detected - may contain specialized configurations")

            if report.version:
                # Check for old Windows versions
                old_versions = ['XP', 'Vista', 'Windows 7', 'Windows 8']
                if any(v in (report.os_name or '') for v in old_versions):
                    recommendations.append("Older Windows version - consider upgrading for security")

            if report.windows_features:
                if report.windows_features.get('has_bitlocker'):
                    recommendations.append("BitLocker detected - ensure you have recovery key before proceeding")

            if len(report.user_profiles) > 5:
                recommendations.append(f"Multiple user profiles ({len(report.user_profiles)}) - review for active vs. dormant accounts")

        if not recommendations:
            recommendations.append("OS detection complete - no issues identified")

        return recommendations

    def _generate_summary(self, report: OSReport) -> str:
        """Generate human-readable summary"""
        parts = []
        parts.append(f"Drive {report.drive_letter}:")

        if report.os_name != 'Unknown':
            parts.append(f"OS: {report.os_name}")
            if report.version:
                parts.append(f"(v{report.version})")
            if report.build_number:
                parts.append(f"Build {report.build_number}")
        else:
            parts.append("OS: Unknown")

        parts.append(f"| Confidence: {report.confidence}")
        parts.append(f"| Method: {report.detection_method}")

        if report.boot_capable:
            parts.append("| Bootable: Yes")

        if report.user_profiles:
            parts.append(f"| Users: {len(report.user_profiles)}")

        if report.errors:
            parts.append(f"| Errors: {len(report.errors)}")

        return " ".join(parts)


def run_os_inspection(drive_path: str, db_path: Optional[str] = None,
                      session_id: Optional[int] = None,
                      include_extra: bool = True,
                      json_output: bool = False) -> Dict[str, Any]:
    """
    Convenience function to run OS detection inspection.

    Args:
        drive_path: Path to drive
        db_path: Optional database path
        session_id: Optional inspection session ID
        include_extra: Include extra analysis (users, features)
        json_output: Return raw dict for JSON serialization

    Returns:
        OS report as dictionary
    """
    inspector = EnhancedOSDetector(db_path)
    report = inspector.inspect(drive_path, session_id, include_extra)

    return report.to_dict()


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Enhanced OS Detection - Pass 2')
    parser.add_argument('drive_path', help='Path to drive (e.g., /mnt/d or D:)')
    parser.add_argument('--db', help='Database path for storing results')
    parser.add_argument('--session', type=int, help='Inspection session ID')
    parser.add_argument('--skip-extra', action='store_true', help='Skip extra analysis')
    parser.add_argument('--json', action='store_true', help='Output as JSON')

    args = parser.parse_args()

    inspector = EnhancedOSDetector(args.db)
    report = inspector.inspect(
        args.drive_path,
        session_id=args.session,
        include_extra_analysis=not args.skip_extra
    )

    if args.json:
        print(report.to_json())
    else:
        print("\n" + "=" * 60)
        print("ENHANCED OS DETECTION REPORT")
        print("=" * 60)
        print(f"\nDrive: {report.drive_letter}: ({report.drive_path})")
        print(f"Time: {report.inspection_time}")
        print(f"\nOS Type: {report.os_type}")
        print(f"OS Name: {report.os_name}")
        if report.version:
            print(f"Version: {report.version}")
        if report.build_number:
            print(f"Build: {report.build_number}")
        if report.edition:
            print(f"Edition: {report.edition}")
        if report.install_date:
            print(f"Install Date: {report.install_date}")
        print(f"\nDetection Method: {report.detection_method}")
        print(f"Confidence: {report.confidence}")
        print(f"Boot Capable: {report.boot_capable}")

        if report.user_profiles:
            print(f"\nUser Profiles ({len(report.user_profiles)}):")
            for user in report.user_profiles[:10]:  # Limit display
                print(f"  - {user}")
            if len(report.user_profiles) > 10:
                print(f"  ... and {len(report.user_profiles) - 10} more")

        if report.windows_features:
            print(f"\nWindows Features:")
            for feature, present in report.windows_features.items():
                if present:
                    print(f"  + {feature}")

        if report.installed_programs_count:
            print(f"\nInstalled Programs: ~{report.installed_programs_count}")

        print(f"\nSummary: {report.summary}")

        if report.errors:
            print(f"\nERRORS ({len(report.errors)}):")
            for error in report.errors:
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
