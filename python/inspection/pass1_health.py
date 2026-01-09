"""
Pass 1: Drive Health Inspector

Performs read-only health assessment of drives:
- Runs chkdsk /scan for filesystem integrity
- Retrieves SMART data if available (for physical drives)
- Generates JSON report suitable for Claude analysis
"""

import os
import json
import platform
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.logger import get_logger
from core.database import Database
from utils.chkdsk_wrapper import ChkdskWrapper, ChkdskResult

logger = get_logger(__name__)


@dataclass
class SmartData:
    """SMART data from drive"""
    available: bool = False
    health_status: str = "Unknown"
    temperature_celsius: Optional[int] = None
    power_on_hours: Optional[int] = None
    power_cycle_count: Optional[int] = None
    reallocated_sectors: Optional[int] = None
    pending_sectors: Optional[int] = None
    uncorrectable_sectors: Optional[int] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    raw_output: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'available': self.available,
            'health_status': self.health_status,
            'temperature_celsius': self.temperature_celsius,
            'power_on_hours': self.power_on_hours,
            'power_cycle_count': self.power_cycle_count,
            'reallocated_sectors': self.reallocated_sectors,
            'pending_sectors': self.pending_sectors,
            'uncorrectable_sectors': self.uncorrectable_sectors,
            'attributes': self.attributes,
            'warnings': self.warnings,
            'raw_output': self.raw_output
        }


@dataclass
class HealthReport:
    """Complete health report for a drive"""
    drive_path: str = ""
    drive_letter: str = ""
    inspection_time: str = ""
    overall_health: str = "Unknown"
    health_score: int = 100  # 0-100, deducted for issues
    chkdsk_result: Optional[Dict[str, Any]] = None
    smart_data: Optional[Dict[str, Any]] = None
    recommendations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'drive_path': self.drive_path,
            'drive_letter': self.drive_letter,
            'inspection_time': self.inspection_time,
            'overall_health': self.overall_health,
            'health_score': self.health_score,
            'chkdsk_result': self.chkdsk_result,
            'smart_data': self.smart_data,
            'recommendations': self.recommendations,
            'warnings': self.warnings,
            'errors': self.errors,
            'summary': self.summary
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), indent=indent, default=str)


class DriveHealthInspector:
    """
    Drive health inspection for Pass 1 of the multi-pass inspection workflow.

    Performs non-destructive health checks:
    1. chkdsk /scan - Filesystem integrity check
    2. SMART data retrieval (if available)

    Generates a JSON report suitable for Claude analysis.
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize the health inspector.

        Args:
            db_path: Path to SQLite database for storing results
        """
        self.is_wsl = self._detect_wsl()
        self.is_windows = platform.system() == 'Windows'
        self.chkdsk_wrapper = ChkdskWrapper()
        self.db = Database(db_path) if db_path else None
        logger.info(f"DriveHealthInspector initialized (WSL: {self.is_wsl}, Windows: {self.is_windows})")

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

    def _find_powershell(self) -> Optional[str]:
        """Find PowerShell executable"""
        if self.is_windows:
            return 'powershell.exe'
        elif self.is_wsl:
            paths = [
                '/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe',
                '/mnt/c/Program Files/PowerShell/7/pwsh.exe',
            ]
            for path in paths:
                if os.path.exists(path):
                    return path
        return None

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
                skip_smart: bool = False, timeout_seconds: int = 300) -> HealthReport:
        """
        Perform complete health inspection on a drive.

        Args:
            drive_path: Path to the drive (e.g., '/mnt/d', 'D:')
            session_id: Optional inspection session ID for database recording
            skip_smart: Skip SMART data retrieval
            timeout_seconds: Timeout for chkdsk operation

        Returns:
            HealthReport with complete inspection results
        """
        report = HealthReport()
        report.drive_path = drive_path
        report.drive_letter = self._extract_drive_letter(drive_path) or "?"
        report.inspection_time = datetime.now().isoformat()

        logger.info(f"Starting health inspection of drive {report.drive_letter}: ({drive_path})")

        # Mark pass as started in database
        if self.db and session_id:
            self.db.start_pass(session_id, 1)

        # Step 1: Run chkdsk
        logger.info("Running chkdsk /scan (this may take a few minutes)...")
        try:
            chkdsk_result = self.chkdsk_wrapper.run_chkdsk(drive_path, timeout_seconds)
            report.chkdsk_result = chkdsk_result.to_dict()

            if chkdsk_result.success:
                logger.info(f"ChkDsk completed in {chkdsk_result.execution_time_seconds:.1f}s")
                if chkdsk_result.errors_found:
                    report.warnings.extend(chkdsk_result.warnings)
                    report.health_score -= 20
                    logger.warning(f"ChkDsk found {len(chkdsk_result.warnings)} warning(s)")
                if chkdsk_result.bad_sectors > 0:
                    report.errors.append(f"Bad sectors detected: {chkdsk_result.bad_sectors}")
                    report.health_score -= 30
                    logger.error(f"Bad sectors found: {chkdsk_result.bad_sectors}")
            else:
                report.warnings.append("ChkDsk did not complete successfully")
                report.warnings.extend(chkdsk_result.errors)
                report.health_score -= 10

        except Exception as e:
            error_msg = f"ChkDsk failed: {str(e)}"
            report.errors.append(error_msg)
            report.health_score -= 15
            logger.error(error_msg)

        # Step 2: Get SMART data
        if not skip_smart:
            logger.info("Retrieving SMART data...")
            try:
                smart_data = self._get_smart_data(drive_path)
                report.smart_data = smart_data.to_dict()

                if smart_data.available:
                    logger.info(f"SMART status: {smart_data.health_status}")
                    if smart_data.health_status.upper() not in ['OK', 'HEALTHY', 'PASS']:
                        report.warnings.append(f"SMART health status: {smart_data.health_status}")
                        report.health_score -= 25

                    # Check critical SMART attributes
                    if smart_data.reallocated_sectors and smart_data.reallocated_sectors > 0:
                        report.warnings.append(f"Reallocated sectors: {smart_data.reallocated_sectors}")
                        report.health_score -= min(smart_data.reallocated_sectors * 2, 20)

                    if smart_data.pending_sectors and smart_data.pending_sectors > 0:
                        report.warnings.append(f"Pending sectors: {smart_data.pending_sectors}")
                        report.health_score -= min(smart_data.pending_sectors * 3, 25)

                    if smart_data.uncorrectable_sectors and smart_data.uncorrectable_sectors > 0:
                        report.errors.append(f"Uncorrectable sectors: {smart_data.uncorrectable_sectors}")
                        report.health_score -= min(smart_data.uncorrectable_sectors * 5, 30)

                    report.warnings.extend(smart_data.warnings)
                else:
                    logger.info("SMART data not available for this drive")
                    report.recommendations.append("SMART data not available - drive may be USB or virtual")

            except Exception as e:
                logger.warning(f"Could not retrieve SMART data: {e}")
                report.recommendations.append(f"SMART data retrieval failed: {str(e)}")

        # Ensure score is within bounds
        report.health_score = max(0, min(100, report.health_score))

        # Determine overall health
        report.overall_health = self._calculate_overall_health(report)

        # Generate recommendations
        report.recommendations.extend(self._generate_recommendations(report))

        # Generate summary
        report.summary = self._generate_summary(report)

        # Store in database
        if self.db and session_id:
            try:
                self.db.complete_pass(
                    session_id, 1,
                    report_json=report.to_json(),
                    error_message='; '.join(report.errors) if report.errors else None
                )
                logger.info(f"Health inspection results saved to database (session {session_id})")
            except Exception as e:
                logger.error(f"Failed to save results to database: {e}")

        logger.info(f"Health inspection complete: {report.overall_health} (score: {report.health_score}/100)")
        return report

    def _get_smart_data(self, drive_path: str) -> SmartData:
        """
        Retrieve SMART data for the drive.

        Uses PowerShell to query Windows for SMART attributes.
        """
        smart = SmartData()
        drive_letter = self._extract_drive_letter(drive_path)

        if not drive_letter:
            return smart

        if not (self.is_windows or self.is_wsl):
            return smart

        powershell = self._find_powershell()
        if not powershell:
            return smart

        # PowerShell script to get SMART data
        ps_script = f"""
$ErrorActionPreference = 'SilentlyContinue'

# Get disk number from drive letter
$partition = Get-Partition -DriveLetter '{drive_letter}' -ErrorAction SilentlyContinue
if (-not $partition) {{
    Write-Output '{{"available": false, "error": "Could not find partition"}}'
    exit
}}
$diskNumber = $partition.DiskNumber

# Get physical disk
$disk = Get-PhysicalDisk -DeviceNumber $diskNumber -ErrorAction SilentlyContinue
if (-not $disk) {{
    Write-Output '{{"available": false, "error": "Could not get physical disk"}}'
    exit
}}

# Get WMI disk info for additional SMART-like data
$wmiDisk = Get-WmiObject -Class Win32_DiskDrive | Where-Object {{$_.Index -eq $diskNumber}}

# Get reliability counters (SMART equivalent in Windows)
$reliability = Get-PhysicalDisk -DeviceNumber $diskNumber | Get-StorageReliabilityCounter -ErrorAction SilentlyContinue

$result = @{{
    available = $true
    health_status = $disk.HealthStatus
    operational_status = $disk.OperationalStatus
    media_type = $disk.MediaType
    bus_type = $disk.BusType
    model = $disk.Model
    serial = $disk.SerialNumber
    firmware = $disk.FirmwareVersion
    size_gb = [math]::Round($disk.Size / 1GB, 2)
}}

if ($reliability) {{
    $result['temperature_celsius'] = $reliability.Temperature
    $result['power_on_hours'] = $reliability.PowerOnHours
    $result['read_errors_total'] = $reliability.ReadErrorsTotal
    $result['read_errors_corrected'] = $reliability.ReadErrorsCorrected
    $result['read_errors_uncorrected'] = $reliability.ReadErrorsUncorrected
    $result['write_errors_total'] = $reliability.WriteErrorsTotal
    $result['write_errors_corrected'] = $reliability.WriteErrorsCorrected
    $result['write_errors_uncorrected'] = $reliability.WriteErrorsUncorrected
    $result['wear'] = $reliability.Wear
}}

$result | ConvertTo-Json -Depth 3
"""

        try:
            result = subprocess.run(
                [powershell, '-Command', ps_script],
                capture_output=True,
                text=True,
                timeout=30
            )

            smart.raw_output = result.stdout

            if result.stdout.strip():
                data = json.loads(result.stdout)

                if data.get('available', False):
                    smart.available = True
                    smart.health_status = data.get('health_status', 'Unknown')
                    smart.temperature_celsius = data.get('temperature_celsius')
                    smart.power_on_hours = data.get('power_on_hours')

                    # Map Windows reliability counters to SMART-like values
                    smart.attributes = {
                        'operational_status': data.get('operational_status'),
                        'media_type': data.get('media_type'),
                        'bus_type': data.get('bus_type'),
                        'model': data.get('model'),
                        'serial': data.get('serial'),
                        'firmware': data.get('firmware'),
                        'size_gb': data.get('size_gb'),
                        'wear': data.get('wear'),
                        'read_errors_total': data.get('read_errors_total'),
                        'read_errors_corrected': data.get('read_errors_corrected'),
                        'read_errors_uncorrected': data.get('read_errors_uncorrected'),
                        'write_errors_total': data.get('write_errors_total'),
                        'write_errors_corrected': data.get('write_errors_corrected'),
                        'write_errors_uncorrected': data.get('write_errors_uncorrected'),
                    }

                    # Calculate sector counts from error data
                    smart.uncorrectable_sectors = (
                        (data.get('read_errors_uncorrected') or 0) +
                        (data.get('write_errors_uncorrected') or 0)
                    )

                    # Generate warnings from SMART data
                    if smart.health_status and smart.health_status.upper() not in ['HEALTHY', 'OK']:
                        smart.warnings.append(f"Health status: {smart.health_status}")

                    if data.get('wear') and data.get('wear') > 80:
                        smart.warnings.append(f"High wear level: {data.get('wear')}%")

                    if data.get('read_errors_uncorrected') and data.get('read_errors_uncorrected') > 0:
                        smart.warnings.append(f"Uncorrected read errors: {data.get('read_errors_uncorrected')}")

                    if data.get('write_errors_uncorrected') and data.get('write_errors_uncorrected') > 0:
                        smart.warnings.append(f"Uncorrected write errors: {data.get('write_errors_uncorrected')}")

                    # Temperature warning
                    if smart.temperature_celsius and smart.temperature_celsius > 55:
                        smart.warnings.append(f"High temperature: {smart.temperature_celsius}C")

        except subprocess.TimeoutExpired:
            logger.warning("SMART data retrieval timed out")
        except json.JSONDecodeError as e:
            logger.warning(f"Could not parse SMART data: {e}")
        except Exception as e:
            logger.warning(f"SMART data retrieval failed: {e}")

        return smart

    def _calculate_overall_health(self, report: HealthReport) -> str:
        """Determine overall health status from score"""
        score = report.health_score

        if score >= 90:
            return "Excellent"
        elif score >= 75:
            return "Good"
        elif score >= 50:
            return "Fair"
        elif score >= 25:
            return "Poor"
        else:
            return "Critical"

    def _generate_recommendations(self, report: HealthReport) -> List[str]:
        """Generate actionable recommendations based on findings"""
        recommendations = []

        if report.health_score < 50:
            recommendations.append("CRITICAL: Back up this drive immediately before proceeding")

        if report.chkdsk_result:
            if report.chkdsk_result.get('bad_sectors', 0) > 0:
                recommendations.append("Bad sectors detected - consider replacing this drive")
            if report.chkdsk_result.get('errors_found'):
                recommendations.append("Run chkdsk /F to fix filesystem errors (requires drive to be offline)")

        if report.smart_data and report.smart_data.get('available'):
            health = report.smart_data.get('health_status', '').upper()
            if health not in ['OK', 'HEALTHY', 'PASS']:
                recommendations.append(f"SMART status is {health} - monitor closely or replace")

            wear = report.smart_data.get('attributes', {}).get('wear')
            if wear and wear > 90:
                recommendations.append(f"SSD wear at {wear}% - plan for replacement")

        if not recommendations:
            recommendations.append("Drive appears healthy - safe to proceed with archival")

        return recommendations

    def _generate_summary(self, report: HealthReport) -> str:
        """Generate human-readable summary"""
        parts = []
        parts.append(f"Drive {report.drive_letter}: Health: {report.overall_health} (Score: {report.health_score}/100)")

        if report.chkdsk_result and report.chkdsk_result.get('success'):
            fs = report.chkdsk_result.get('filesystem_type', 'Unknown')
            errors = "errors found" if report.chkdsk_result.get('errors_found') else "no errors"
            parts.append(f"Filesystem: {fs}, ChkDsk: {errors}")

        if report.smart_data and report.smart_data.get('available'):
            status = report.smart_data.get('health_status', 'Unknown')
            parts.append(f"SMART: {status}")
            temp = report.smart_data.get('temperature_celsius')
            if temp:
                parts.append(f"Temperature: {temp}C")

        if report.errors:
            parts.append(f"Errors: {len(report.errors)}")
        if report.warnings:
            parts.append(f"Warnings: {len(report.warnings)}")

        return " | ".join(parts)


def run_health_inspection(drive_path: str, db_path: Optional[str] = None,
                          session_id: Optional[int] = None,
                          skip_smart: bool = False,
                          json_output: bool = False) -> Dict[str, Any]:
    """
    Convenience function to run health inspection.

    Args:
        drive_path: Path to drive
        db_path: Optional database path
        session_id: Optional inspection session ID
        skip_smart: Skip SMART data retrieval
        json_output: Return raw dict for JSON serialization

    Returns:
        Health report as dictionary
    """
    inspector = DriveHealthInspector(db_path)
    report = inspector.inspect(drive_path, session_id, skip_smart)

    if json_output:
        return report.to_dict()
    return report.to_dict()


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Drive Health Inspector - Pass 1')
    parser.add_argument('drive_path', help='Path to drive (e.g., /mnt/d or D:)')
    parser.add_argument('--db', help='Database path for storing results')
    parser.add_argument('--session', type=int, help='Inspection session ID')
    parser.add_argument('--skip-smart', action='store_true', help='Skip SMART data retrieval')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument('--timeout', type=int, default=300, help='Timeout for chkdsk (seconds)')

    args = parser.parse_args()

    inspector = DriveHealthInspector(args.db)
    report = inspector.inspect(
        args.drive_path,
        session_id=args.session,
        skip_smart=args.skip_smart,
        timeout_seconds=args.timeout
    )

    if args.json:
        print(report.to_json())
    else:
        print("\n" + "=" * 60)
        print("DRIVE HEALTH INSPECTION REPORT")
        print("=" * 60)
        print(f"\nDrive: {report.drive_letter}: ({report.drive_path})")
        print(f"Time: {report.inspection_time}")
        print(f"\nOverall Health: {report.overall_health}")
        print(f"Health Score: {report.health_score}/100")
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
