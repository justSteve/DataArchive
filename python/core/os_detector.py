"""
Operating system detection
"""

import os
import re
from pathlib import Path
from typing import Dict, Any, Optional

from .logger import get_logger

logger = get_logger(__name__)


class OSDetector:
    """Detect operating system on drives"""
    
    def __init__(self, drive_path: str):
        self.drive_path = Path(drive_path)
        logger.debug(f"OSDetector initialized for: {drive_path}")
    
    def detect(self) -> Dict[str, Any]:
        """Main detection method - tries all approaches"""
        result = {
            'os_type': 'Unknown',
            'os_name': 'Unknown',
            'version': None,
            'build_number': None,
            'edition': None,
            'install_date': None,
            'boot_capable': False,
            'detection_method': None,
            'confidence': 'UNKNOWN',
            'methods_tried': []
        }
        
        # Try Windows detection
        windows_result = self._detect_windows()
        if windows_result['confidence'] != 'UNKNOWN':
            result.update(windows_result)
            return result
        
        # Try Linux detection
        linux_result = self._detect_linux()
        if linux_result['confidence'] != 'UNKNOWN':
            result.update(linux_result)
            return result
        
        # Try Mac detection
        mac_result = self._detect_mac()
        if mac_result['confidence'] != 'UNKNOWN':
            result.update(mac_result)
            return result
        
        logger.info(f"Could not detect OS on {self.drive_path}")
        return result
    
    def _detect_windows(self) -> Dict[str, Any]:
        """Detect Windows OS"""
        result = {
            'os_type': 'Windows',
            'confidence': 'UNKNOWN',
            'methods_tried': []
        }
        
        # Method 1: Check for Windows folder
        windows_path = self.drive_path / 'Windows'
        if not windows_path.exists():
            return result
        
        result['methods_tried'].append('windows_folder_found')
        result['boot_capable'] = True
        
        # Method 2: Pattern recognition
        pattern_result = self._detect_windows_by_pattern()
        if pattern_result['confidence'] != 'UNKNOWN':
            result.update(pattern_result)
            return result
        
        # Method 3: Check version files (simplified)
        version_result = self._detect_windows_by_files()
        if version_result['confidence'] != 'UNKNOWN':
            result.update(version_result)
            return result
        
        # At least we know it's Windows
        result['confidence'] = 'LOW'
        result['os_name'] = 'Windows (version unknown)'
        result['detection_method'] = 'PATTERN'
        
        return result
    
    def _detect_windows_by_pattern(self) -> Dict[str, Any]:
        """Detect Windows version by folder patterns"""
        result = {
            'confidence': 'UNKNOWN',
            'detection_method': 'PATTERN'
        }
        
        # Check for User/Program Files structure
        users_path = self.drive_path / 'Users'
        docs_settings_path = self.drive_path / 'Documents and Settings'
        program_files_x86 = self.drive_path / 'Program Files (x86)'
        
        if users_path.exists() and program_files_x86.exists():
            # Windows Vista+ 64-bit
            result['os_name'] = 'Windows 7/8/10/11 (64-bit)'
            result['confidence'] = 'MEDIUM'
        elif users_path.exists():
            # Windows Vista+
            result['os_name'] = 'Windows Vista or later'
            result['confidence'] = 'LOW'
        elif docs_settings_path.exists():
            # Windows XP or earlier
            result['os_name'] = 'Windows XP or earlier'
            result['confidence'] = 'LOW'
        elif (self.drive_path / 'WINNT').exists():
            # Windows NT/2000
            result['os_name'] = 'Windows NT/2000'
            result['confidence'] = 'MEDIUM'
        
        return result
    
    def _detect_windows_by_files(self) -> Dict[str, Any]:
        """Detect Windows by checking version files"""
        result = {
            'confidence': 'UNKNOWN',
            'detection_method': 'FILES'
        }
        
        # Check for specific version indicators
        version_files = {
            'Windows/System32/ntoskrnl.exe': 'NT Kernel',
            'Windows/System32/kernel32.dll': 'Kernel32',
        }
        
        for file_path, description in version_files.items():
            full_path = self.drive_path / file_path
            if full_path.exists():
                result['confidence'] = 'MEDIUM'
                result['methods_tried'] = [f'found_{description}']
                logger.debug(f"Found {description} at {full_path}")
                break
        
        return result
    
    def _detect_linux(self) -> Dict[str, Any]:
        """Detect Linux OS"""
        result = {
            'os_type': 'Linux',
            'confidence': 'UNKNOWN',
            'methods_tried': []
        }
        
        # Check for /etc directory
        etc_path = self.drive_path / 'etc'
        if not etc_path.exists():
            return result
        
        result['boot_capable'] = True
        result['methods_tried'].append('etc_folder_found')
        
        # Try to read os-release
        os_release_path = etc_path / 'os-release'
        if os_release_path.exists():
            try:
                with open(os_release_path, 'r') as f:
                    content = f.read()
                    
                    # Parse NAME and VERSION
                    name_match = re.search(r'NAME="?([^"\n]+)"?', content)
                    version_match = re.search(r'VERSION="?([^"\n]+)"?', content)
                    
                    if name_match:
                        result['os_name'] = name_match.group(1)
                        result['confidence'] = 'HIGH'
                        result['detection_method'] = 'OS_RELEASE'
                    
                    if version_match:
                        result['version'] = version_match.group(1)
                
                return result
            except Exception as e:
                logger.debug(f"Could not read os-release: {e}")
        
        # Fallback
        result['os_name'] = 'Linux (distribution unknown)'
        result['confidence'] = 'LOW'
        result['detection_method'] = 'PATTERN'
        
        return result
    
    def _detect_mac(self) -> Dict[str, Any]:
        """Detect macOS"""
        result = {
            'os_type': 'Mac',
            'confidence': 'UNKNOWN',
            'methods_tried': []
        }
        
        # Check for System/Library
        system_path = self.drive_path / 'System' / 'Library'
        if not system_path.exists():
            return result
        
        result['boot_capable'] = True
        result['os_name'] = 'macOS (version unknown)'
        result['confidence'] = 'LOW'
        result['detection_method'] = 'PATTERN'
        result['methods_tried'].append('system_library_found')
        
        return result
