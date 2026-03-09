"""
Drive Metadata Exporter

Exports drive hardware metadata to a dedicated folder structure:
output/drives/{DRIVE_CODE}/

Files created:
- hardware.json: Drive hardware details (serial, model, capacity, etc.)
- windows_install.json: Windows installation details (if Windows boot drive)
- scan_summary.json: Summary of scan results
"""

import json
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional


def get_drive_hardware_info(mount_point: str) -> Dict[str, Any]:
    """
    Get hardware information for a drive

    Args:
        mount_point: Drive mount point (e.g., '/mnt/d', 'D:')

    Returns:
        Dictionary with hardware details
    """
    info = {
        'mount_point': mount_point,
        'collected_at': datetime.now().isoformat(),
        'serial_number': None,
        'model': None,
        'manufacturer': None,
        'size_bytes': None,
        'filesystem': None,
        'connection_type': None,
        'media_type': None,
    }

    try:
        # Try to get info via PowerShell (works from WSL)
        drive_letter = _extract_drive_letter(mount_point)
        if drive_letter:
            ps_script = f"""
            $disk = Get-Partition -DriveLetter {drive_letter} | Get-Disk
            $volume = Get-Volume -DriveLetter {drive_letter}

            [PSCustomObject]@{{
                SerialNumber = $disk.SerialNumber
                Model = $disk.Model
                Manufacturer = $disk.Manufacturer
                Size = $disk.Size
                MediaType = $disk.MediaType
                BusType = $disk.BusType
                FileSystem = $volume.FileSystem
            }} | ConvertTo-Json
            """

            result = subprocess.run(
                ['powershell.exe', '-Command', ps_script],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0 and result.stdout:
                ps_data = json.loads(result.stdout)
                info.update({
                    'serial_number': ps_data.get('SerialNumber'),
                    'model': ps_data.get('Model'),
                    'manufacturer': ps_data.get('Manufacturer'),
                    'size_bytes': ps_data.get('Size'),
                    'filesystem': ps_data.get('FileSystem'),
                    'connection_type': ps_data.get('BusType'),
                    'media_type': ps_data.get('MediaType'),
                })

    except Exception as e:
        info['error'] = f"Failed to retrieve hardware info: {e}"

    return info


def get_windows_install_info(mount_point: str) -> Optional[Dict[str, Any]]:
    """
    Get Windows installation details from registry

    Args:
        mount_point: Drive mount point

    Returns:
        Dictionary with Windows installation details, or None if not Windows
    """
    from pathlib import Path

    drive_path = Path(mount_point)
    registry_path = drive_path / 'Windows' / 'System32' / 'config' / 'SOFTWARE'

    try:
        if not registry_path.exists():
            return None
    except (PermissionError, OSError):
        # Registry files often have restricted permissions
        # Try alternative detection
        windows_dir = drive_path / 'Windows'
        if not windows_dir.exists():
            return None

    info = {
        'detected': True,
        'registry_path': str(registry_path),
        'collected_at': datetime.now().isoformat(),
        'product_name': None,
        'version': None,
        'build': None,
        'edition': None,
        'install_date': None,
    }

    try:
        # Try reading registry via PowerShell (offline registry access)
        drive_letter = _extract_drive_letter(mount_point)
        if drive_letter:
            ps_script = f"""
            $regPath = '{drive_letter}:\\Windows\\System32\\config\\SOFTWARE'

            # Load the offline registry hive
            reg load HKLM\\TempHive $regPath 2>&1 | Out-Null

            if ($?) {{
                $key = 'HKLM:\\TempHive\\Microsoft\\Windows NT\\CurrentVersion'
                $productName = (Get-ItemProperty -Path $key -Name ProductName -ErrorAction SilentlyContinue).ProductName
                $displayVersion = (Get-ItemProperty -Path $key -Name DisplayVersion -ErrorAction SilentlyContinue).DisplayVersion
                $currentBuild = (Get-ItemProperty -Path $key -Name CurrentBuild -ErrorAction SilentlyContinue).CurrentBuild
                $editionID = (Get-ItemProperty -Path $key -Name EditionID -ErrorAction SilentlyContinue).EditionID
                $installDate = (Get-ItemProperty -Path $key -Name InstallDate -ErrorAction SilentlyContinue).InstallDate

                [PSCustomObject]@{{
                    ProductName = $productName
                    DisplayVersion = $displayVersion
                    CurrentBuild = $currentBuild
                    EditionID = $editionID
                    InstallDate = $installDate
                }} | ConvertTo-Json

                # Unload the hive
                reg unload HKLM\\TempHive 2>&1 | Out-Null
            }}
            """

            result = subprocess.run(
                ['powershell.exe', '-Command', ps_script],
                capture_output=True,
                text=True,
                timeout=15
            )

            if result.returncode == 0 and result.stdout:
                ps_data = json.loads(result.stdout)

                # Convert InstallDate from Unix timestamp if present
                install_date_unix = ps_data.get('InstallDate')
                install_date_formatted = None
                if install_date_unix:
                    try:
                        install_date_formatted = datetime.fromtimestamp(install_date_unix).isoformat()
                    except:
                        pass

                info.update({
                    'product_name': ps_data.get('ProductName'),
                    'version': ps_data.get('DisplayVersion'),
                    'build': ps_data.get('CurrentBuild'),
                    'edition': ps_data.get('EditionID'),
                    'install_date': install_date_formatted,
                })

    except Exception as e:
        info['error'] = f"Failed to read Windows registry: {e}"

    return info


def export_drive_metadata(drive_code: str, mount_point: str,
                          output_base: str = 'output/drives') -> Path:
    """
    Export drive metadata to folder structure

    Args:
        drive_code: 4-character drive code (e.g., 'EXLP')
        mount_point: Drive mount point
        output_base: Base output directory

    Returns:
        Path to created drive folder
    """
    # Create drive folder
    drive_folder = Path(output_base) / drive_code
    drive_folder.mkdir(parents=True, exist_ok=True)

    # Export hardware info
    hardware_info = get_drive_hardware_info(mount_point)
    hardware_file = drive_folder / 'hardware.json'
    with open(hardware_file, 'w') as f:
        json.dump(hardware_info, f, indent=2, default=str)

    print(f"✓ Exported hardware metadata to {hardware_file}")

    # Export Windows install info (if applicable)
    windows_info = get_windows_install_info(mount_point)
    if windows_info:
        windows_file = drive_folder / 'windows_install.json'
        with open(windows_file, 'w') as f:
            json.dump(windows_info, f, indent=2, default=str)
        print(f"✓ Exported Windows installation details to {windows_file}")

    return drive_folder


def _extract_drive_letter(mount_point: str) -> Optional[str]:
    """Extract Windows drive letter from mount point"""
    import re

    if len(mount_point) >= 1 and mount_point[1:2] == ':':
        return mount_point[0].upper()

    match = re.match(r'^/mnt/([a-zA-Z])(?:/|$)', mount_point)
    if match:
        return match.group(1).upper()

    return None


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Export drive metadata')
    parser.add_argument('drive_code', help='4-character drive code (e.g., EXLP)')
    parser.add_argument('mount_point', help='Drive mount point (e.g., /mnt/d)')
    parser.add_argument('--output', default='output/drives', help='Output base directory')

    args = parser.parse_args()

    folder = export_drive_metadata(args.drive_code, args.mount_point, args.output)
    print(f"\n✓ Drive metadata exported to {folder}")
