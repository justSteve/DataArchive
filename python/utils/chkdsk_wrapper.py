"""
ChkDsk wrapper for drive health inspection.

Provides cross-platform execution of Windows chkdsk utility from both
native Windows and WSL environments.
"""

import os
import re
import platform
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ChkdskResult:
    """Results from a chkdsk scan"""
    success: bool = False
    drive_letter: str = ""
    volume_label: str = ""
    filesystem_type: str = ""
    total_bytes: int = 0
    used_bytes: int = 0
    free_bytes: int = 0
    allocation_unit_bytes: int = 0
    total_allocation_units: int = 0

    # Health indicators
    errors_found: bool = False
    bad_sectors: int = 0
    stage_results: List[Dict[str, Any]] = field(default_factory=list)

    # Warnings and errors
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    # Raw output for Claude analysis
    raw_output: str = ""
    exit_code: int = -1
    execution_time_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'success': self.success,
            'drive_letter': self.drive_letter,
            'volume_label': self.volume_label,
            'filesystem_type': self.filesystem_type,
            'total_bytes': self.total_bytes,
            'used_bytes': self.used_bytes,
            'free_bytes': self.free_bytes,
            'allocation_unit_bytes': self.allocation_unit_bytes,
            'total_allocation_units': self.total_allocation_units,
            'errors_found': self.errors_found,
            'bad_sectors': self.bad_sectors,
            'stage_results': self.stage_results,
            'warnings': self.warnings,
            'errors': self.errors,
            'raw_output': self.raw_output,
            'exit_code': self.exit_code,
            'execution_time_seconds': self.execution_time_seconds
        }


class ChkdskWrapper:
    """
    Wrapper for Windows chkdsk command with cross-platform support.

    Supports execution from:
    - Native Windows
    - WSL (via powershell.exe)

    Uses read-only scan mode (/scan) to avoid modifying the drive.
    """

    def __init__(self):
        self.is_wsl = self._detect_wsl()
        self.is_windows = platform.system() == 'Windows'
        self.powershell_path = self._find_powershell()

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
        """Find the PowerShell executable path"""
        if self.is_windows:
            return 'powershell.exe'
        elif self.is_wsl:
            # Common WSL locations for PowerShell
            paths = [
                '/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe',
                '/mnt/c/Program Files/PowerShell/7/pwsh.exe',
            ]
            for path in paths:
                if os.path.exists(path):
                    return path
            # Try using the PATH
            try:
                result = subprocess.run(['which', 'powershell.exe'],
                                       capture_output=True, text=True)
                if result.returncode == 0:
                    return result.stdout.strip()
            except Exception:
                pass
        return None

    def can_run_chkdsk(self) -> bool:
        """Check if chkdsk can be executed"""
        if not (self.is_windows or self.is_wsl):
            logger.warning("ChkDsk only available on Windows or WSL")
            return False
        if self.is_wsl and not self.powershell_path:
            logger.warning("Could not find PowerShell in WSL environment")
            return False
        return True

    def _extract_drive_letter(self, drive_path: str) -> Optional[str]:
        """Extract Windows drive letter from path"""
        # Handle Windows paths like C:\ or C:
        if len(drive_path) >= 1 and drive_path[1:2] == ':':
            return drive_path[0].upper()

        # Handle WSL paths like /mnt/c or /mnt/c/something
        match = re.match(r'^/mnt/([a-zA-Z])(?:/|$)', drive_path)
        if match:
            return match.group(1).upper()

        return None

    def run_chkdsk(self, drive_path: str, timeout_seconds: int = 300) -> ChkdskResult:
        """
        Run chkdsk /scan on the specified drive.

        Uses /scan mode which is read-only and runs online without requiring
        the volume to be taken offline.

        Args:
            drive_path: Path to drive (e.g., 'D:', '/mnt/d', 'D:\\')
            timeout_seconds: Maximum time to wait for chkdsk (default 5 minutes)

        Returns:
            ChkdskResult with parsed output and health indicators
        """
        result = ChkdskResult()

        drive_letter = self._extract_drive_letter(drive_path)
        if not drive_letter:
            result.errors.append(f"Could not extract drive letter from path: {drive_path}")
            return result

        result.drive_letter = drive_letter

        if not self.can_run_chkdsk():
            result.errors.append("ChkDsk is not available in this environment")
            return result

        logger.info(f"Running chkdsk /scan on drive {drive_letter}:")

        start_time = datetime.now()

        try:
            if self.is_wsl:
                output, exit_code = self._run_chkdsk_wsl(drive_letter, timeout_seconds)
            else:
                output, exit_code = self._run_chkdsk_windows(drive_letter, timeout_seconds)

            result.raw_output = output
            result.exit_code = exit_code
            result.execution_time_seconds = (datetime.now() - start_time).total_seconds()

            # Parse the output
            self._parse_chkdsk_output(output, result)

            # Success if we got output and no critical errors
            result.success = bool(output) and exit_code in [0, 1]  # 1 = errors found but completed

        except subprocess.TimeoutExpired:
            result.errors.append(f"ChkDsk timed out after {timeout_seconds} seconds")
            result.execution_time_seconds = timeout_seconds
            logger.error(f"ChkDsk timed out on drive {drive_letter}:")

        except Exception as e:
            result.errors.append(f"ChkDsk execution failed: {str(e)}")
            logger.error(f"ChkDsk failed: {e}")

        return result

    def _run_chkdsk_wsl(self, drive_letter: str, timeout_seconds: int) -> tuple:
        """Run chkdsk from WSL using PowerShell"""
        # PowerShell script to run chkdsk with elevated privileges if needed
        # Note: /scan mode doesn't require elevation for read-only check
        ps_command = f"""
            $ErrorActionPreference = 'Continue'
            $output = chkdsk {drive_letter}: /scan 2>&1 | Out-String
            Write-Output $output
            exit $LASTEXITCODE
        """

        process = subprocess.run(
            [self.powershell_path, '-Command', ps_command],
            capture_output=True,
            text=True,
            timeout=timeout_seconds
        )

        # Combine stdout and stderr
        output = process.stdout
        if process.stderr:
            output += "\n--- STDERR ---\n" + process.stderr

        return output, process.returncode

    def _run_chkdsk_windows(self, drive_letter: str, timeout_seconds: int) -> tuple:
        """Run chkdsk on native Windows"""
        process = subprocess.run(
            ['chkdsk', f'{drive_letter}:', '/scan'],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            shell=True  # Required on Windows
        )

        output = process.stdout
        if process.stderr:
            output += "\n--- STDERR ---\n" + process.stderr

        return output, process.returncode

    def _parse_chkdsk_output(self, output: str, result: ChkdskResult) -> None:
        """Parse chkdsk output and populate result"""
        if not output:
            return

        lines = output.split('\n')
        current_stage = None

        for line in lines:
            line = line.strip()

            # Volume label and filesystem
            if 'volume label is' in line.lower():
                match = re.search(r'volume label is (.+)', line, re.IGNORECASE)
                if match:
                    result.volume_label = match.group(1).strip()

            # Filesystem type
            if 'file system is' in line.lower():
                match = re.search(r'file system is (\w+)', line, re.IGNORECASE)
                if match:
                    result.filesystem_type = match.group(1).upper()

            # Stage detection
            stage_match = re.search(r'stage (\d+) of (\d+)', line, re.IGNORECASE)
            if stage_match:
                current_stage = {
                    'stage_number': int(stage_match.group(1)),
                    'total_stages': int(stage_match.group(2)),
                    'description': line,
                    'status': 'running'
                }
                result.stage_results.append(current_stage)

            # Stage completion
            if current_stage and 'percent complete' in line.lower():
                if '100 percent' in line.lower():
                    current_stage['status'] = 'completed'

            # Bad sectors
            bad_sectors_match = re.search(r'(\d+)\s+(?:KB|bytes)\s+in bad sectors', line, re.IGNORECASE)
            if bad_sectors_match:
                result.bad_sectors = int(bad_sectors_match.group(1))
                if result.bad_sectors > 0:
                    result.errors_found = True
                    result.warnings.append(f"Bad sectors detected: {result.bad_sectors}")

            # Total space
            total_match = re.search(r'([\d,]+)\s+(?:KB|bytes|MB|GB)\s+total disk space', line, re.IGNORECASE)
            if total_match:
                value = int(total_match.group(1).replace(',', ''))
                # Convert to bytes (assume KB if not specified)
                if 'GB' in line.upper():
                    result.total_bytes = value * 1024 * 1024 * 1024
                elif 'MB' in line.upper():
                    result.total_bytes = value * 1024 * 1024
                elif 'KB' in line.upper():
                    result.total_bytes = value * 1024
                else:
                    result.total_bytes = value

            # Free space
            free_match = re.search(r'([\d,]+)\s+(?:KB|bytes|MB|GB)\s+(?:are )?available', line, re.IGNORECASE)
            if free_match:
                value = int(free_match.group(1).replace(',', ''))
                if 'GB' in line.upper():
                    result.free_bytes = value * 1024 * 1024 * 1024
                elif 'MB' in line.upper():
                    result.free_bytes = value * 1024 * 1024
                elif 'KB' in line.upper():
                    result.free_bytes = value * 1024
                else:
                    result.free_bytes = value

            # Allocation unit size
            alloc_match = re.search(r'([\d,]+)\s+bytes\s+(?:in each )?allocation unit', line, re.IGNORECASE)
            if alloc_match:
                result.allocation_unit_bytes = int(alloc_match.group(1).replace(',', ''))

            # Error detection keywords
            error_keywords = [
                'error', 'corrupt', 'damaged', 'failed', 'unreadable',
                'lost chain', 'cross-linked', 'invalid'
            ]
            for keyword in error_keywords:
                if keyword in line.lower() and 'no errors' not in line.lower():
                    # Avoid false positives
                    if not any(exclude in line.lower() for exclude in
                              ['error-free', 'no errors found', 'windows has scanned']):
                        result.errors_found = True
                        if line not in result.warnings:
                            result.warnings.append(line)

            # Clean completion messages
            if 'windows has scanned the file system and found no problems' in line.lower():
                result.errors_found = False

            if 'no further action is required' in line.lower():
                result.errors_found = False

        # Calculate used bytes
        if result.total_bytes > 0 and result.free_bytes > 0:
            result.used_bytes = result.total_bytes - result.free_bytes


def run_chkdsk(drive_path: str, timeout_seconds: int = 300) -> Dict[str, Any]:
    """
    Convenience function to run chkdsk and return results as a dictionary.

    Args:
        drive_path: Path to drive (e.g., 'D:', '/mnt/d')
        timeout_seconds: Maximum execution time

    Returns:
        Dictionary with chkdsk results
    """
    wrapper = ChkdskWrapper()
    result = wrapper.run_chkdsk(drive_path, timeout_seconds)
    return result.to_dict()


if __name__ == '__main__':
    import json
    import sys

    if len(sys.argv) < 2:
        print("Usage: python chkdsk_wrapper.py <drive_path>")
        print("Example: python chkdsk_wrapper.py /mnt/d")
        print("Example: python chkdsk_wrapper.py D:")
        sys.exit(1)

    drive_path = sys.argv[1]
    result = run_chkdsk(drive_path)
    print(json.dumps(result, indent=2))
