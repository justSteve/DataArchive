"""
Windows Registry Reader for offline drive inspection.

Provides functionality to read Windows Registry hives from mounted drives
without requiring the drive to be the active Windows installation.

Works from both Windows native and WSL environments.
"""

import os
import re
import struct
import platform
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RegistryValue:
    """A registry value with its data"""
    name: str
    value_type: str
    data: Any
    raw_data: Optional[bytes] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'type': self.value_type,
            'data': self.data
        }


@dataclass
class RegistryKey:
    """A registry key with its values and subkeys"""
    path: str
    values: Dict[str, RegistryValue] = field(default_factory=dict)
    subkeys: List[str] = field(default_factory=list)
    last_modified: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'path': self.path,
            'values': {k: v.to_dict() for k, v in self.values.items()},
            'subkeys': self.subkeys,
            'last_modified': self.last_modified.isoformat() if self.last_modified else None
        }


@dataclass
class RegistryReadResult:
    """Result of a registry read operation"""
    success: bool = False
    key: Optional[RegistryKey] = None
    error: Optional[str] = None
    method_used: str = ""
    raw_output: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            'success': self.success,
            'key': self.key.to_dict() if self.key else None,
            'error': self.error,
            'method_used': self.method_used
        }


class RegistryReader:
    """
    Reads Windows Registry hives from offline drives.

    Supports multiple methods:
    1. PowerShell reg.exe load/query/unload (requires elevation on Windows)
    2. PowerShell direct hive reading
    3. Python hivex library if available (pure Python, no elevation)

    The registry hives are located at:
    - HKLM\\SOFTWARE -> Windows\\System32\\config\\SOFTWARE
    - HKLM\\SYSTEM -> Windows\\System32\\config\\SYSTEM
    - HKCU -> Users\\<username>\\NTUSER.DAT
    """

    # Registry value type mappings
    REG_TYPES = {
        0: 'REG_NONE',
        1: 'REG_SZ',
        2: 'REG_EXPAND_SZ',
        3: 'REG_BINARY',
        4: 'REG_DWORD',
        5: 'REG_DWORD_BIG_ENDIAN',
        6: 'REG_LINK',
        7: 'REG_MULTI_SZ',
        8: 'REG_RESOURCE_LIST',
        9: 'REG_FULL_RESOURCE_DESCRIPTOR',
        10: 'REG_RESOURCE_REQUIREMENTS_LIST',
        11: 'REG_QWORD'
    }

    def __init__(self, drive_path: str):
        """
        Initialize registry reader for a specific drive.

        Args:
            drive_path: Path to the mounted drive (e.g., '/mnt/d', 'D:')
        """
        self.drive_path = Path(drive_path)
        self.is_wsl = self._detect_wsl()
        self.is_windows = platform.system() == 'Windows'
        self.powershell_path = self._find_powershell()
        self._hivex_available = self._check_hivex()

        logger.debug(f"RegistryReader initialized for {drive_path}")
        logger.debug(f"  WSL: {self.is_wsl}, Windows: {self.is_windows}")
        logger.debug(f"  PowerShell: {self.powershell_path}")
        logger.debug(f"  Hivex available: {self._hivex_available}")

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

    def _check_hivex(self) -> bool:
        """Check if hivex library is available"""
        try:
            import hivex
            return True
        except ImportError:
            return False

    def _get_hive_path(self, hive_name: str) -> Optional[Path]:
        """
        Get the path to a registry hive file on the drive.

        Args:
            hive_name: One of 'SOFTWARE', 'SYSTEM', 'SAM', 'SECURITY', 'DEFAULT'

        Returns:
            Path to the hive file or None if not found
        """
        config_path = self.drive_path / 'Windows' / 'System32' / 'config'

        if not config_path.exists():
            logger.warning(f"Config path not found: {config_path}")
            return None

        hive_file = config_path / hive_name
        if hive_file.exists():
            return hive_file

        # Try lowercase
        hive_file = config_path / hive_name.lower()
        if hive_file.exists():
            return hive_file

        logger.warning(f"Hive file not found: {hive_file}")
        return None

    def _extract_drive_letter(self) -> Optional[str]:
        """Extract Windows drive letter from drive path"""
        path_str = str(self.drive_path)

        # Handle Windows paths like D:\ or D:
        if len(path_str) >= 1 and path_str[1:2] == ':':
            return path_str[0].upper()

        # Handle WSL paths like /mnt/d
        match = re.match(r'^/mnt/([a-zA-Z])(?:/|$)', path_str)
        if match:
            return match.group(1).upper()

        return None

    def read_key(self, hive: str, key_path: str) -> RegistryReadResult:
        """
        Read a registry key from an offline hive.

        Args:
            hive: Hive name ('SOFTWARE', 'SYSTEM', etc.)
            key_path: Path within the hive (e.g., 'Microsoft\\Windows NT\\CurrentVersion')

        Returns:
            RegistryReadResult with key data or error
        """
        result = RegistryReadResult()

        # Try hivex first (no elevation required)
        if self._hivex_available:
            hivex_result = self._read_with_hivex(hive, key_path)
            if hivex_result.success:
                return hivex_result
            logger.debug(f"Hivex method failed: {hivex_result.error}")

        # Try PowerShell method
        if self.powershell_path:
            ps_result = self._read_with_powershell(hive, key_path)
            if ps_result.success:
                return ps_result
            logger.debug(f"PowerShell method failed: {ps_result.error}")

        result.error = "No available method could read the registry"
        return result

    def _read_with_hivex(self, hive: str, key_path: str) -> RegistryReadResult:
        """Read registry using hivex library"""
        result = RegistryReadResult(method_used='hivex')

        try:
            import hivex

            hive_path = self._get_hive_path(hive)
            if not hive_path:
                result.error = f"Hive file not found for {hive}"
                return result

            h = hivex.Hivex(str(hive_path))

            # Navigate to the key
            key_parts = key_path.strip('\\').split('\\')
            node = h.root()

            for part in key_parts:
                if not part:
                    continue
                found = False
                for child in h.node_children(node):
                    if h.node_name(child).lower() == part.lower():
                        node = child
                        found = True
                        break
                if not found:
                    result.error = f"Key not found: {key_path}"
                    h.close()
                    return result

            # Read values
            reg_key = RegistryKey(path=key_path)

            for value in h.node_values(node):
                name = h.value_key(value) or "(Default)"
                val_type = h.value_type(value)[0]
                type_name = self.REG_TYPES.get(val_type, f'Unknown({val_type})')

                try:
                    data = h.value_value(value)[1]
                    parsed_data = self._parse_value_data(val_type, data)
                except Exception as e:
                    parsed_data = f"<error: {e}>"

                reg_key.values[name] = RegistryValue(
                    name=name,
                    value_type=type_name,
                    data=parsed_data
                )

            # Get subkeys
            for child in h.node_children(node):
                reg_key.subkeys.append(h.node_name(child))

            h.close()

            result.success = True
            result.key = reg_key

        except ImportError:
            result.error = "hivex library not available"
        except Exception as e:
            result.error = f"hivex error: {str(e)}"
            logger.exception("Hivex read failed")

        return result

    def _read_with_powershell(self, hive: str, key_path: str) -> RegistryReadResult:
        """
        Read registry using PowerShell.

        This method uses reg.exe to load the hive temporarily, query it,
        then unload. Requires elevation on Windows.
        """
        result = RegistryReadResult(method_used='powershell')

        hive_path = self._get_hive_path(hive)
        if not hive_path:
            result.error = f"Hive file not found for {hive}"
            return result

        # Convert path for PowerShell
        if self.is_wsl:
            # Convert /mnt/d/path to D:\path
            drive_letter = self._extract_drive_letter()
            if drive_letter:
                hive_path_str = str(hive_path).replace(str(self.drive_path), f'{drive_letter}:')
                hive_path_str = hive_path_str.replace('/', '\\')
            else:
                result.error = "Could not extract drive letter for WSL path"
                return result
        else:
            hive_path_str = str(hive_path)

        # PowerShell script to load hive, read key, unload
        # Uses a unique temp key name to avoid conflicts
        temp_key_name = f"TEMP_OFFLINE_{hive}_{os.getpid()}"

        ps_script = f"""
$ErrorActionPreference = 'Stop'

$hivePath = '{hive_path_str}'
$tempKeyName = '{temp_key_name}'
$keyPath = '{key_path}'

$result = @{{
    success = $false
    values = @{{}}
    subkeys = @()
    error = $null
}}

try {{
    # Load the hive
    $loadResult = reg load "HKLM\\$tempKeyName" "$hivePath" 2>&1
    if ($LASTEXITCODE -ne 0) {{
        throw "Failed to load hive: $loadResult"
    }}

    # Query the key
    $fullKeyPath = "HKLM\\$tempKeyName\\$keyPath"

    # Get values
    try {{
        $regKey = Get-ItemProperty -Path "Registry::$fullKeyPath" -ErrorAction Stop
        foreach ($prop in $regKey.PSObject.Properties) {{
            if ($prop.Name -notmatch '^PS') {{
                $result.values[$prop.Name] = @{{
                    name = $prop.Name
                    type = $prop.TypeNameOfValue
                    data = $prop.Value
                }}
            }}
        }}
    }} catch {{
        # Key might not have values, continue
    }}

    # Get subkeys
    try {{
        $subkeys = Get-ChildItem -Path "Registry::$fullKeyPath" -ErrorAction Stop
        $result.subkeys = @($subkeys | ForEach-Object {{ $_.PSChildName }})
    }} catch {{
        # Key might not have subkeys
    }}

    $result.success = $true

}} catch {{
    $result.error = $_.Exception.Message
}} finally {{
    # Always try to unload the hive
    try {{
        [gc]::Collect()
        Start-Sleep -Milliseconds 100
        reg unload "HKLM\\$tempKeyName" 2>&1 | Out-Null
    }} catch {{
        # Ignore unload errors
    }}
}}

$result | ConvertTo-Json -Depth 4
"""

        try:
            proc = subprocess.run(
                [self.powershell_path, '-Command', ps_script],
                capture_output=True,
                text=True,
                timeout=30
            )

            result.raw_output = proc.stdout

            if proc.stdout.strip():
                import json
                data = json.loads(proc.stdout)

                if data.get('success'):
                    reg_key = RegistryKey(path=key_path)

                    for name, val_info in data.get('values', {}).items():
                        reg_key.values[name] = RegistryValue(
                            name=name,
                            value_type=val_info.get('type', 'Unknown'),
                            data=val_info.get('data')
                        )

                    reg_key.subkeys = data.get('subkeys', [])

                    result.success = True
                    result.key = reg_key
                else:
                    result.error = data.get('error', 'Unknown error')
            else:
                result.error = proc.stderr or "No output from PowerShell"

        except subprocess.TimeoutExpired:
            result.error = "PowerShell command timed out"
        except json.JSONDecodeError as e:
            result.error = f"Failed to parse PowerShell output: {e}"
        except Exception as e:
            result.error = f"PowerShell execution failed: {e}"

        return result

    def _parse_value_data(self, value_type: int, data: bytes) -> Any:
        """Parse registry value data based on type"""
        if value_type == 1:  # REG_SZ
            try:
                return data.decode('utf-16-le').rstrip('\x00')
            except:
                return data.decode('utf-8', errors='replace').rstrip('\x00')

        elif value_type == 2:  # REG_EXPAND_SZ
            try:
                return data.decode('utf-16-le').rstrip('\x00')
            except:
                return data.decode('utf-8', errors='replace').rstrip('\x00')

        elif value_type == 3:  # REG_BINARY
            return data.hex()

        elif value_type == 4:  # REG_DWORD
            if len(data) >= 4:
                return struct.unpack('<I', data[:4])[0]
            return None

        elif value_type == 5:  # REG_DWORD_BIG_ENDIAN
            if len(data) >= 4:
                return struct.unpack('>I', data[:4])[0]
            return None

        elif value_type == 7:  # REG_MULTI_SZ
            try:
                decoded = data.decode('utf-16-le')
                return [s for s in decoded.split('\x00') if s]
            except:
                return [data.decode('utf-8', errors='replace')]

        elif value_type == 11:  # REG_QWORD
            if len(data) >= 8:
                return struct.unpack('<Q', data[:8])[0]
            return None

        else:
            return data.hex() if data else None

    def read_windows_version(self) -> Dict[str, Any]:
        """
        Read Windows version information from the SOFTWARE hive.

        Returns a dictionary with:
        - ProductName
        - DisplayVersion
        - CurrentBuild
        - EditionID
        - InstallDate
        - And other version-related values
        """
        result = {
            'success': False,
            'product_name': None,
            'display_version': None,
            'current_build': None,
            'edition_id': None,
            'install_date': None,
            'registered_owner': None,
            'registered_organization': None,
            'system_root': None,
            'build_lab': None,
            'build_lab_ex': None,
            'current_version': None,
            'ubr': None,  # Update Build Revision
            'raw_values': {},
            'method_used': None,
            'error': None
        }

        # Read from SOFTWARE\Microsoft\Windows NT\CurrentVersion
        key_path = "Microsoft\\Windows NT\\CurrentVersion"
        read_result = self.read_key('SOFTWARE', key_path)

        if not read_result.success:
            result['error'] = read_result.error
            return result

        result['success'] = True
        result['method_used'] = read_result.method_used

        key = read_result.key
        values = key.values

        # Map common values
        value_mapping = {
            'ProductName': 'product_name',
            'DisplayVersion': 'display_version',
            'CurrentBuild': 'current_build',
            'CurrentBuildNumber': 'current_build',  # Fallback
            'EditionID': 'edition_id',
            'InstallDate': 'install_date',
            'RegisteredOwner': 'registered_owner',
            'RegisteredOrganization': 'registered_organization',
            'SystemRoot': 'system_root',
            'BuildLab': 'build_lab',
            'BuildLabEx': 'build_lab_ex',
            'CurrentVersion': 'current_version',
            'UBR': 'ubr'
        }

        for reg_name, result_key in value_mapping.items():
            if reg_name in values:
                val = values[reg_name]
                result[result_key] = val.data
                result['raw_values'][reg_name] = val.to_dict()

        # Parse InstallDate if it's a Unix timestamp
        if result['install_date']:
            try:
                if isinstance(result['install_date'], int):
                    result['install_date_parsed'] = datetime.fromtimestamp(
                        result['install_date']
                    ).isoformat()
            except Exception:
                pass

        return result


def read_offline_registry(drive_path: str, hive: str, key_path: str) -> Dict[str, Any]:
    """
    Convenience function to read a registry key from an offline drive.

    Args:
        drive_path: Path to mounted drive
        hive: Hive name (SOFTWARE, SYSTEM, etc.)
        key_path: Key path within the hive

    Returns:
        Dictionary with key data or error
    """
    reader = RegistryReader(drive_path)
    result = reader.read_key(hive, key_path)
    return result.to_dict()


def get_windows_version(drive_path: str) -> Dict[str, Any]:
    """
    Convenience function to get Windows version from an offline drive.

    Args:
        drive_path: Path to mounted drive

    Returns:
        Dictionary with Windows version info
    """
    reader = RegistryReader(drive_path)
    return reader.read_windows_version()


if __name__ == '__main__':
    import json
    import sys

    if len(sys.argv) < 2:
        print("Usage: python registry_reader.py <drive_path> [hive] [key_path]")
        print("\nExamples:")
        print("  python registry_reader.py /mnt/d")
        print("    - Get Windows version info")
        print("  python registry_reader.py D: SOFTWARE \"Microsoft\\Windows NT\\CurrentVersion\"")
        print("    - Read specific registry key")
        sys.exit(1)

    drive_path = sys.argv[1]

    if len(sys.argv) >= 4:
        # Read specific key
        hive = sys.argv[2]
        key_path = sys.argv[3]
        result = read_offline_registry(drive_path, hive, key_path)
    else:
        # Get Windows version
        result = get_windows_version(drive_path)

    print(json.dumps(result, indent=2, default=str))
