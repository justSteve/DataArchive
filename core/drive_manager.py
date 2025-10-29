"""
Drive detection and management with proper hardware identification
"""

import os
import re
import shutil
import platform
import subprocess
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from .logger import get_logger

logger = get_logger(__name__)


class DriveManager:
    """Detect and manage drives with proper hardware identification"""
    
    def __init__(self):
        self.platform = self._detect_platform()
        logger.info(f"Platform detected: {self.platform}")
    
    def _detect_platform(self) -> str:
        """Detect if running in WSL or bare metal"""
        if os.path.exists('/proc/sys/fs/binfmt_misc/WSLInterop'):
            return 'WSL'
        elif platform.system() == 'Linux':
            return 'LINUX'
        elif platform.system() == 'Windows':
            return 'WINDOWS'
        else:
            return 'UNKNOWN'
    
    def get_physical_drive_identity(self, mount_path: str) -> Dict[str, Any]:
        """
        Get the actual physical drive identity (not the dock/interface).
        This is critical for archival - we want to track the DRIVE, not the adapter.
        """
        if self.platform != 'WSL':
            logger.warning("Physical drive identification currently only supported in WSL")
            return self._fallback_identity(mount_path)
        
        try:
            # Get the Windows disk number from the mount point
            disk_number = self._get_disk_number_from_mount(mount_path)
            if disk_number is None:
                logger.warning(f"Could not determine disk number for {mount_path}")
                return self._fallback_identity(mount_path)
            
            # Query Windows for the actual drive identity
            ps_command = f"""
                $disk = Get-PhysicalDisk -DeviceNumber {disk_number}
                $diskDrive = Get-WmiObject -Class Win32_DiskDrive | Where-Object {{$_.Index -eq {disk_number}}}
                
                @{{
                    SerialNumber = $disk.SerialNumber
                    Model = $disk.Model
                    MediaType = $disk.MediaType
                    BusType = $disk.BusType
                    Manufacturer = $disk.Manufacturer
                    FirmwareVersion = $disk.FirmwareVersion
                    Size = $disk.Size
                    WmiModel = $diskDrive.Model
                    WmiSerial = $diskDrive.SerialNumber
                    InterfaceType = $diskDrive.InterfaceType
                }} | ConvertTo-Json
            """
            
            result = subprocess.run(
                ['/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe', 
                 '-Command', ps_command],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                
                # Clean up serial numbers (remove whitespace)
                serial = (data.get('SerialNumber') or data.get('WmiSerial') or '').strip()
                model = (data.get('Model') or data.get('WmiModel') or 'Unknown').strip()
                
                identity = {
                    'serial_number': serial if serial else f"UNKNOWN_{mount_path.replace('/', '_')}",
                    'model': model,
                    'manufacturer': data.get('Manufacturer', 'Unknown'),
                    'firmware_version': data.get('FirmwareVersion', 'Unknown'),
                    'size_bytes': int(data.get('Size', 0)) if data.get('Size') else 0,
                    'media_type': data.get('MediaType', 'Unknown'),  # HDD, SSD, etc.
                    'bus_type': data.get('BusType', 'Unknown'),  # SATA, USB, NVMe, etc.
                    'interface_type': data.get('InterfaceType', 'Unknown'),
                    'connection_method': 'Direct' if data.get('BusType') in ['SATA', 'NVMe', 'IDE'] else 'USB/Bridge',
                    'disk_number': disk_number
                }
                
                logger.info(f"✓ Identified drive: {identity['model']} (S/N: {identity['serial_number']})")
                return identity
            else:
                logger.warning(f"PowerShell query failed: {result.stderr}")
                return self._fallback_identity(mount_path)
                
        except subprocess.TimeoutExpired:
            logger.warning("PowerShell query timed out")
            return self._fallback_identity(mount_path)
        except Exception as e:
            logger.warning(f"Error getting physical drive identity: {e}")
            return self._fallback_identity(mount_path)
    
    def _get_disk_number_from_mount(self, mount_path: str) -> Optional[int]:
        """
        Determine Windows disk number from WSL mount point.
        E.g., /mnt/e -> Disk number for E: drive
        """
        try:
            # Extract drive letter from path
            path_parts = Path(mount_path).parts
            if len(path_parts) > 1 and path_parts[0] == '/' and path_parts[1] == 'mnt':
                if len(path_parts) > 2:
                    drive_letter = path_parts[2].upper()
                else:
                    # Just /mnt/x
                    drive_letter = Path(mount_path).name.upper()
            else:
                logger.warning(f"Path {mount_path} doesn't match expected /mnt/X format")
                return None
            
            # Query Windows for the disk number of this drive letter
            ps_command = f"""
                $partition = Get-Partition -DriveLetter {drive_letter} -ErrorAction SilentlyContinue
                if ($partition) {{
                    $partition.DiskNumber
                }}
            """
            
            result = subprocess.run(
                ['/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe',
                 '-Command', ps_command],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0 and result.stdout.strip():
                disk_num = int(result.stdout.strip())
                logger.debug(f"Drive {drive_letter}: = Disk {disk_num}")
                return disk_num
            else:
                logger.warning(f"Could not get disk number for drive {drive_letter}:")
                return None
                
        except Exception as e:
            logger.warning(f"Error determining disk number: {e}")
            return None
    
    def _fallback_identity(self, mount_path: str) -> Dict[str, Any]:
        """Fallback identity when we can't get real drive info"""
        import hashlib
        from datetime import datetime
        
        # Create a pseudo-identifier based on path
        path_hash = hashlib.md5(mount_path.encode()).hexdigest()[:16]
        
        return {
            'serial_number': f"UNKNOWN_{path_hash}",
            'model': f"Unknown Drive at {mount_path}",
            'manufacturer': 'Unknown',
            'firmware_version': 'Unknown',
            'size_bytes': 0,
            'media_type': 'Unknown',
            'bus_type': 'Unknown',
            'interface_type': 'Unknown',
            'connection_method': 'Unknown',
            'disk_number': None,
            'note': 'Could not retrieve physical drive identity'
        }
    
    def detect_drives(self) -> List[Dict[str, Any]]:
        """Detect all available drives"""
        if self.platform == 'WSL':
            return self._detect_wsl_drives()
        elif self.platform == 'LINUX':
            return self._detect_linux_drives()
        elif self.platform == 'WINDOWS':
            return self._detect_windows_drives()
        else:
            logger.error(f"Unsupported platform: {self.platform}")
            return []
    
    def _detect_wsl_drives(self) -> List[Dict[str, Any]]:
        """Detect Windows drives mounted in WSL"""
        drives = []
        
        # Check /mnt/* for Windows drives
        mnt_path = Path('/mnt')
        if mnt_path.exists():
            for letter_path in mnt_path.iterdir():
                if letter_path.is_dir() and len(letter_path.name) == 1:
                    try:
                        stat = os.statvfs(str(letter_path))
                        total = stat.f_blocks * stat.f_frsize
                        free = stat.f_bavail * stat.f_frsize
                        
                        mount_point = str(letter_path)
                        identity = self.get_physical_drive_identity(mount_point)
                        
                        drives.append({
                            'device': f"{letter_path.name.upper()}:",
                            'mount_point': mount_point,
                            'size_bytes': total,
                            'free_bytes': free,
                            'filesystem': self._get_filesystem_type(mount_point),
                            'connection_type': 'WSL',
                            **identity  # Include all physical drive identity info
                        })
                        logger.debug(f"Detected WSL drive: {letter_path.name.upper()}:")
                    except (OSError, PermissionError) as e:
                        logger.warning(f"Could not access {letter_path}: {e}")
                        continue
        
        return drives
    
    def _detect_linux_drives(self) -> List[Dict[str, Any]]:
        """Detect block devices on Linux"""
        drives = []
        logger.warning("Linux bare metal drive detection not yet implemented")
        return drives
    
    def _detect_windows_drives(self) -> List[Dict[str, Any]]:
        """Detect drives on Windows"""
        drives = []
        logger.warning("Windows drive detection not yet implemented")
        return drives
    
    def _get_filesystem_type(self, mount_point: str) -> Optional[str]:
        """Get filesystem type"""
        try:
            with open('/proc/mounts', 'r') as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 3 and parts[1] == mount_point:
                        return parts[2]
        except Exception as e:
            logger.debug(f"Could not determine filesystem type: {e}")
        return None
    
    def is_drive_accessible(self, path: str) -> bool:
        """Check if drive is accessible"""
        try:
            path_obj = Path(path)
            return path_obj.exists() and path_obj.is_dir()
        except Exception as e:
            logger.error(f"Drive not accessible: {path} - {e}")
            return False
    
    def get_drive_info(self, path: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific drive"""
        if not self.is_drive_accessible(path):
            return None
        
        try:
            stat = os.statvfs(path)
            total = stat.f_blocks * stat.f_frsize
            free = stat.f_bavail * stat.f_frsize
            used = total - free
            
            # Get physical drive identity
            identity = self.get_physical_drive_identity(path)
            
            return {
                'path': path,
                'total_bytes': total,
                'used_bytes': used,
                'free_bytes': free,
                'filesystem': self._get_filesystem_type(path),
                'accessible': True,
                **identity  # Include physical drive identity
            }
        except Exception as e:
            logger.error(f"Error getting drive info for {path}: {e}")
            return None
