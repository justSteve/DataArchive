"""
Drive validation utilities for ensuring drive is properly mounted and accessible
"""

import subprocess
import re
from pathlib import Path
from typing import Optional, Dict, Any, List

from .logger import get_logger

logger = get_logger(__name__)


class DriveValidator:
    """
    Validates drive connectivity and readiness before scanning.
    Catches common issues like missing drive numbers, offline disks, etc.
    """
    
    def __init__(self, mount_path: str):
        self.mount_path = Path(mount_path)
        self.is_wsl = self._detect_wsl()
    
    def _detect_wsl(self) -> bool:
        """Detect if running in WSL"""
        try:
            with open('/proc/version', 'r') as f:
                return 'microsoft' in f.read().lower() or 'wsl' in f.read().lower()
        except Exception:
            return False
    
    def validate(self) -> Dict[str, Any]:
        """
        Comprehensive drive validation.
        Returns validation results with warnings and errors.
        """
        results = {
            'valid': True,
            'warnings': [],
            'errors': [],
            'drive_info': {},
            'recommendations': []
        }
        
        # Basic path checks
        if not self.mount_path.exists():
            results['valid'] = False
            results['errors'].append(f"Path does not exist: {self.mount_path}")
            return results
        
        if not self.mount_path.is_dir():
            results['valid'] = False
            results['errors'].append(f"Path is not a directory: {self.mount_path}")
            return results
        
        # WSL-specific validation
        if self.is_wsl:
            wsl_results = self._validate_wsl_mount()
            results['drive_info'].update(wsl_results.get('drive_info', {}))
            results['warnings'].extend(wsl_results.get('warnings', []))
            results['errors'].extend(wsl_results.get('errors', []))
            
            if wsl_results.get('errors'):
                results['valid'] = False
        
        # Check if path is accessible
        try:
            # Try to list directory
            list(self.mount_path.iterdir())
        except PermissionError:
            results['valid'] = False
            results['errors'].append(f"Permission denied accessing {self.mount_path}")
        except Exception as e:
            results['valid'] = False
            results['errors'].append(f"Cannot access {self.mount_path}: {e}")
        
        return results
    
    def _validate_wsl_mount(self) -> Dict[str, Any]:
        """Validate WSL-mounted Windows drive"""
        results = {
            'warnings': [],
            'errors': [],
            'drive_info': {}
        }
        
        try:
            # Extract drive letter from path
            path_parts = self.mount_path.parts
            if len(path_parts) < 2 or path_parts[1] != 'mnt':
                results['warnings'].append(
                    f"Path {self.mount_path} doesn't follow /mnt/X pattern - may not be a Windows drive"
                )
                return results
            
            if len(path_parts) < 3:
                results['errors'].append("Cannot determine drive letter from path")
                return results
            
            drive_letter = path_parts[2].upper()
            results['drive_info']['drive_letter'] = drive_letter
            
            # Query Windows for drive status
            ps_script = f"""
                $disk = Get-Partition -DriveLetter {drive_letter} -ErrorAction SilentlyContinue | Select-Object -First 1
                if ($disk) {{
                    $diskInfo = Get-Disk -Number $disk.DiskNumber
                    $physDisk = Get-PhysicalDisk -DeviceNumber $disk.DiskNumber -ErrorAction SilentlyContinue
                    
                    @{{
                        DiskNumber = $disk.DiskNumber
                        PartitionNumber = $disk.PartitionNumber
                        DriveLetter = $disk.DriveLetter
                        Size = $disk.Size
                        DiskStatus = $diskInfo.OperationalStatus
                        PartitionStyle = $diskInfo.PartitionStyle
                        IsOffline = $diskInfo.IsOffline
                        IsReadOnly = $diskInfo.IsReadOnly
                        PhysicalDiskFound = ($physDisk -ne $null)
                        Model = if ($physDisk) {{ $physDisk.Model }} else {{ "Unknown" }}
                        SerialNumber = if ($physDisk) {{ $physDisk.SerialNumber }} else {{ "Unknown" }}
                        MediaType = if ($physDisk) {{ $physDisk.MediaType }} else {{ "Unknown" }}
                    }} | ConvertTo-Json
                }} else {{
                    @{{ Error = "Drive not found" }} | ConvertTo-Json
                }}
            """
            
            result = subprocess.run(
                ['/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe',
                 '-Command', ps_script],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                results['warnings'].append(
                    f"Could not query Windows drive status (may require admin privileges)"
                )
                return results
            
            import json
            drive_data = json.loads(result.stdout)
            
            if 'Error' in drive_data:
                results['errors'].append(
                    f"Drive {drive_letter}: not found in Windows. "
                    f"The path exists in WSL but Windows doesn't recognize it."
                )
                return results
            
            # Store drive info
            results['drive_info'].update(drive_data)
            
            # Check for issues
            if drive_data.get('IsOffline'):
                results['errors'].append(
                    f"Drive {drive_letter}: (Disk {drive_data['DiskNumber']}) is OFFLINE. "
                    f"Bring it online first: Set-Disk -Number {drive_data['DiskNumber']} -IsOffline $false"
                )
            
            if drive_data.get('IsReadOnly'):
                results['warnings'].append(
                    f"Drive {drive_letter}: is READ-ONLY. Scan will work but no modifications possible."
                )
            
            if drive_data.get('DiskStatus') != 'Online':
                results['warnings'].append(
                    f"Drive status: {drive_data.get('DiskStatus')} (expected 'Online')"
                )
            
            # Check for the PhysicalDisk number bug
            if not drive_data.get('PhysicalDiskFound'):
                results['warnings'].append(
                    "Note: Windows PowerShell Get-PhysicalDisk bug detected - "
                    "drive number may not display correctly in some commands, but drive is functional"
                )
            
            # Log success info
            logger.debug(f"Drive validation successful:")
            logger.debug(f"  Drive: {drive_letter}: → Disk {drive_data['DiskNumber']}, "
                        f"Partition {drive_data['PartitionNumber']}")
            logger.debug(f"  Model: {drive_data.get('Model')}")
            logger.debug(f"  Serial: {drive_data.get('SerialNumber')}")
            logger.debug(f"  Status: {drive_data.get('DiskStatus')}")
            
        except subprocess.TimeoutExpired:
            results['warnings'].append("Drive validation timed out - continuing anyway")
        except Exception as e:
            results['warnings'].append(f"Drive validation error: {e}")
        
        return results
    
    def print_validation_report(self, results: Dict[str, Any]) -> None:
        """Print a formatted validation report"""
        
        logger.info("\n" + "="*60)
        logger.info("DRIVE VALIDATION REPORT")
        logger.info("="*60)
        
        # Drive info
        drive_info = results.get('drive_info', {})
        if drive_info:
            logger.info("\nDrive Information:")
            if 'drive_letter' in drive_info:
                logger.info(f"  Drive Letter: {drive_info['drive_letter']}:")
            if 'DiskNumber' in drive_info:
                logger.info(f"  Windows Disk Number: {drive_info['DiskNumber']}")
            if 'PartitionNumber' in drive_info:
                logger.info(f"  Partition Number: {drive_info['PartitionNumber']}")
            if 'Model' in drive_info:
                logger.info(f"  Model: {drive_info['Model']}")
            if 'SerialNumber' in drive_info:
                logger.info(f"  Serial: {drive_info['SerialNumber']}")
            if 'MediaType' in drive_info:
                logger.info(f"  Media Type: {drive_info['MediaType']}")
            if 'DiskStatus' in drive_info:
                logger.info(f"  Status: {drive_info['DiskStatus']}")
        
        # Errors
        if results['errors']:
            logger.info("\n❌ ERRORS (must be fixed):")
            for error in results['errors']:
                logger.error(f"  • {error}")
        
        # Warnings
        if results['warnings']:
            logger.info("\n⚠️  WARNINGS (should review):")
            for warning in results['warnings']:
                logger.warning(f"  • {warning}")
        
        # Overall status
        logger.info("\n" + "="*60)
        if results['valid']:
            logger.info("✓ Drive validation PASSED - ready to scan")
        else:
            logger.info("✗ Drive validation FAILED - cannot scan")
        logger.info("="*60 + "\n")
