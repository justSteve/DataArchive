"""
Enhanced Operating System Detection

Provides multi-method OS detection for drives:
1. Registry-based detection (primary for Windows - high confidence)
2. Pattern-based detection (fallback - medium/low confidence)
3. File-based detection (Linux, macOS)

Supports detection from both Windows native and WSL environments.
"""

import os
import re
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from .logger import get_logger

logger = get_logger(__name__)


@dataclass
class OSDetectionResult:
    """Result of OS detection with confidence level"""
    os_type: str = "Unknown"
    os_name: str = "Unknown"
    version: Optional[str] = None
    build_number: Optional[str] = None
    edition: Optional[str] = None
    install_date: Optional[str] = None
    boot_capable: bool = False
    detection_method: str = "NONE"
    confidence: str = "UNKNOWN"  # HIGH, MEDIUM, LOW, UNKNOWN
    methods_tried: List[str] = field(default_factory=list)
    raw_data: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
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
            'raw_data': self.raw_data,
            'errors': self.errors
        }


class OSDetector:
    """
    Multi-method operating system detection.

    Detects OS information from mounted drives using:
    - Windows: Registry reading (preferred) or pattern matching
    - Linux: /etc/os-release parsing
    - macOS: System/Library structure detection
    """

    def __init__(self, drive_path: str):
        """
        Initialize OS detector for a specific drive.

        Args:
            drive_path: Path to the mounted drive
        """
        self.drive_path = Path(drive_path)
        self._registry_reader = None
        logger.debug(f"OSDetector initialized for: {drive_path}")

    def _get_registry_reader(self):
        """Lazy-load registry reader to avoid import issues"""
        if self._registry_reader is None:
            try:
                from utils.registry_reader import RegistryReader
                self._registry_reader = RegistryReader(str(self.drive_path))
            except ImportError:
                logger.warning("Registry reader not available")
                self._registry_reader = False
        return self._registry_reader if self._registry_reader else None

    def detect(self) -> OSDetectionResult:
        """
        Main detection method - tries all approaches in order of reliability.

        Returns:
            OSDetectionResult with OS information and confidence level
        """
        result = OSDetectionResult()

        # Try Windows detection
        windows_result = self._detect_windows()
        if windows_result.confidence != 'UNKNOWN':
            return windows_result

        # Try Linux detection
        linux_result = self._detect_linux()
        if linux_result.confidence != 'UNKNOWN':
            return linux_result

        # Try Mac detection
        mac_result = self._detect_mac()
        if mac_result.confidence != 'UNKNOWN':
            return mac_result

        logger.info(f"Could not detect OS on {self.drive_path}")
        return result

    def _detect_windows(self) -> OSDetectionResult:
        """
        Detect Windows OS using multiple methods.

        Priority:
        1. Registry reading (HIGH confidence)
        2. Pattern matching (MEDIUM/LOW confidence)
        """
        result = OSDetectionResult(os_type='Windows')

        # Check for Windows folder first
        windows_path = self.drive_path / 'Windows'
        if not windows_path.exists():
            result.confidence = 'UNKNOWN'
            return result

        result.boot_capable = True
        result.methods_tried.append('windows_folder_found')

        # Method 1: Registry-based detection (HIGH confidence)
        registry_result = self._detect_windows_by_registry()
        if registry_result.confidence == 'HIGH':
            return registry_result

        # Method 2: Pattern-based detection (MEDIUM/LOW confidence)
        pattern_result = self._detect_windows_by_pattern()
        if pattern_result.confidence != 'UNKNOWN':
            # Merge any partial registry data
            if registry_result.raw_data:
                pattern_result.raw_data.update(registry_result.raw_data)
            return pattern_result

        # Fallback: We know it's Windows but can't determine version
        result.confidence = 'LOW'
        result.os_name = 'Windows (version unknown)'
        result.detection_method = 'PATTERN'
        result.methods_tried.extend(registry_result.methods_tried)
        result.errors.extend(registry_result.errors)

        return result

    def _detect_windows_by_registry(self) -> OSDetectionResult:
        """
        Detect Windows version by reading the registry.

        Reads: HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion
        """
        result = OSDetectionResult(os_type='Windows')
        result.methods_tried.append('registry_read')

        reader = self._get_registry_reader()
        if not reader:
            result.errors.append("Registry reader not available")
            return result

        try:
            version_info = reader.read_windows_version()

            if not version_info.get('success'):
                result.errors.append(version_info.get('error', 'Unknown registry error'))
                return result

            result.raw_data = version_info.get('raw_values', {})

            # Extract key fields
            product_name = version_info.get('product_name')
            display_version = version_info.get('display_version')
            current_build = version_info.get('current_build')
            edition_id = version_info.get('edition_id')
            install_date = version_info.get('install_date_parsed') or version_info.get('install_date')
            ubr = version_info.get('ubr')

            if product_name:
                result.os_name = product_name
                result.confidence = 'HIGH'
                result.detection_method = 'REGISTRY'
                result.boot_capable = True

                if display_version:
                    result.version = display_version
                elif version_info.get('current_version'):
                    result.version = version_info.get('current_version')

                if current_build:
                    if ubr:
                        result.build_number = f"{current_build}.{ubr}"
                    else:
                        result.build_number = str(current_build)

                if edition_id:
                    result.edition = edition_id

                if install_date:
                    result.install_date = str(install_date)

                logger.info(f"Registry detection: {result.os_name} (Build {result.build_number})")
            else:
                result.errors.append("ProductName not found in registry")

        except Exception as e:
            result.errors.append(f"Registry read exception: {str(e)}")
            logger.exception("Registry detection failed")

        return result

    def _detect_windows_by_pattern(self) -> OSDetectionResult:
        """
        Detect Windows version by folder patterns.

        Uses directory structure to infer Windows version when registry
        is not accessible.
        """
        result = OSDetectionResult(os_type='Windows')
        result.methods_tried.append('pattern_match')
        result.detection_method = 'PATTERN'
        result.boot_capable = True

        # Check for characteristic folders
        users_path = self.drive_path / 'Users'
        docs_settings_path = self.drive_path / 'Documents and Settings'
        program_files_x86 = self.drive_path / 'Program Files (x86)'
        winnt_path = self.drive_path / 'WINNT'

        # Windows 10/11 indicators
        windows_apps = self.drive_path / 'Program Files' / 'WindowsApps'
        win_sxs = self.drive_path / 'Windows' / 'WinSxS'

        if users_path.exists() and program_files_x86.exists():
            # Windows Vista+ 64-bit
            if windows_apps.exists():
                # Windows 8+ (has WindowsApps for UWP)
                result.os_name = 'Windows 8/10/11 (64-bit)'
                result.confidence = 'MEDIUM'

                # Try to refine based on specific markers
                if (self.drive_path / 'Windows' / 'System32' / 'WinBioDatabase').exists():
                    result.os_name = 'Windows 10/11 (64-bit)'
            else:
                result.os_name = 'Windows Vista/7/8 (64-bit)'
                result.confidence = 'MEDIUM'

        elif users_path.exists():
            # Windows Vista+ 32-bit
            result.os_name = 'Windows Vista or later (32-bit)'
            result.confidence = 'LOW'

        elif docs_settings_path.exists():
            # Windows XP or earlier
            result.os_name = 'Windows XP or earlier'
            result.confidence = 'MEDIUM'

        elif winnt_path.exists():
            # Windows NT/2000
            result.os_name = 'Windows NT/2000'
            result.confidence = 'MEDIUM'

        else:
            result.os_name = 'Windows (version unknown)'
            result.confidence = 'LOW'

        # Check for kernel files to confirm
        if (self.drive_path / 'Windows' / 'System32' / 'ntoskrnl.exe').exists():
            result.methods_tried.append('ntoskrnl_found')
        if (self.drive_path / 'Windows' / 'System32' / 'kernel32.dll').exists():
            result.methods_tried.append('kernel32_found')

        return result

    def _detect_linux(self) -> OSDetectionResult:
        """
        Detect Linux OS by reading /etc/os-release.
        """
        result = OSDetectionResult(os_type='Linux')

        # Check for /etc directory
        etc_path = self.drive_path / 'etc'
        if not etc_path.exists():
            result.confidence = 'UNKNOWN'
            return result

        result.boot_capable = True
        result.methods_tried.append('etc_folder_found')

        # Try to read os-release
        os_release_path = etc_path / 'os-release'
        if os_release_path.exists():
            try:
                with open(os_release_path, 'r') as f:
                    content = f.read()
                    result.raw_data['os_release'] = content

                    # Parse key fields
                    parsers = {
                        'NAME': lambda m: setattr(result, 'os_name', m.group(1).strip('"')),
                        'VERSION': lambda m: setattr(result, 'version', m.group(1).strip('"')),
                        'VERSION_ID': lambda m: setattr(result, 'build_number', m.group(1).strip('"')),
                        'ID': lambda m: result.raw_data.update({'distribution': m.group(1).strip('"')}),
                    }

                    for key, handler in parsers.items():
                        match = re.search(rf'^{key}="?([^"\n]+)"?', content, re.MULTILINE)
                        if match:
                            handler(match)

                    if result.os_name and result.os_name != 'Unknown':
                        result.confidence = 'HIGH'
                        result.detection_method = 'OS_RELEASE'
                        logger.info(f"Linux detected: {result.os_name} {result.version}")
                        return result

            except Exception as e:
                result.errors.append(f"Could not read os-release: {e}")
                logger.debug(f"Could not read os-release: {e}")

        # Try lsb-release fallback
        lsb_release_path = etc_path / 'lsb-release'
        if lsb_release_path.exists():
            try:
                with open(lsb_release_path, 'r') as f:
                    content = f.read()
                    result.raw_data['lsb_release'] = content

                    distrib_match = re.search(r'DISTRIB_DESCRIPTION="?([^"\n]+)"?', content)
                    if distrib_match:
                        result.os_name = distrib_match.group(1)
                        result.confidence = 'MEDIUM'
                        result.detection_method = 'LSB_RELEASE'
                        return result

            except Exception as e:
                result.errors.append(f"Could not read lsb-release: {e}")

        # Fallback
        result.os_name = 'Linux (distribution unknown)'
        result.confidence = 'LOW'
        result.detection_method = 'PATTERN'

        return result

    def _detect_mac(self) -> OSDetectionResult:
        """
        Detect macOS by checking System/Library structure.
        """
        result = OSDetectionResult(os_type='macOS')

        # Check for System/Library
        system_library = self.drive_path / 'System' / 'Library'
        if not system_library.exists():
            result.confidence = 'UNKNOWN'
            return result

        result.boot_capable = True
        result.methods_tried.append('system_library_found')

        # Try to read SystemVersion.plist
        system_version_path = system_library / 'CoreServices' / 'SystemVersion.plist'
        if system_version_path.exists():
            try:
                # Try to parse plist (would need plistlib)
                import plistlib
                with open(system_version_path, 'rb') as f:
                    plist = plistlib.load(f)
                    result.raw_data['SystemVersion'] = plist

                    result.os_name = plist.get('ProductName', 'macOS')
                    result.version = plist.get('ProductUserVisibleVersion')
                    result.build_number = plist.get('ProductBuildVersion')

                    if result.version:
                        result.confidence = 'HIGH'
                        result.detection_method = 'SYSTEM_VERSION_PLIST'
                        logger.info(f"macOS detected: {result.os_name} {result.version}")
                        return result

            except ImportError:
                result.errors.append("plistlib not available")
            except Exception as e:
                result.errors.append(f"Could not read SystemVersion.plist: {e}")

        # Fallback
        result.os_name = 'macOS (version unknown)'
        result.confidence = 'LOW'
        result.detection_method = 'PATTERN'

        return result


def detect_os(drive_path: str) -> Dict[str, Any]:
    """
    Convenience function to detect OS on a drive.

    Args:
        drive_path: Path to the mounted drive

    Returns:
        Dictionary with OS detection results
    """
    detector = OSDetector(drive_path)
    result = detector.detect()
    return result.to_dict()


if __name__ == '__main__':
    import json
    import sys

    if len(sys.argv) < 2:
        print("Usage: python os_detector.py <drive_path>")
        print("Example: python os_detector.py /mnt/d")
        print("Example: python os_detector.py D:")
        sys.exit(1)

    drive_path = sys.argv[1]
    result = detect_os(drive_path)
    print(json.dumps(result, indent=2, default=str))
