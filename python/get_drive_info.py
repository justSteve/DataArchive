#!/usr/bin/env python3
"""
Get drive hardware information
Returns JSON with drive serial, model, etc.
"""

import sys
import json
import argparse
import logging
from pathlib import Path

# Suppress all logging before importing modules
logging.disable(logging.CRITICAL)

from core.drive_manager import DriveManager

def main():
    parser = argparse.ArgumentParser(description='Get drive hardware information')
    parser.add_argument('drive_path', help='Path to drive (e.g., /mnt/e)')
    args = parser.parse_args()

    drive_path = Path(args.drive_path)

    # Validate path exists
    if not drive_path.exists():
        print(json.dumps({
            'success': False,
            'error': f'Drive path does not exist: {drive_path}'
        }))
        return 1

    try:
        # Get drive info
        drive_mgr = DriveManager()
        drive_info = drive_mgr.get_drive_info(str(drive_path))

        # Return as JSON
        result = {
            'success': True,
            'drive_info': {
                'serial_number': drive_info.get('serial_number', f'UNKNOWN_{drive_path.name}'),
                'model': drive_info.get('model', f'Drive at {drive_path}'),
                'manufacturer': drive_info.get('manufacturer'),
                'size_bytes': drive_info.get('total_bytes', 0),
                'filesystem': drive_info.get('filesystem'),
                'connection_type': drive_info.get('connection_method', 'unknown'),
                'media_type': drive_info.get('media_type'),
                'bus_type': drive_info.get('bus_type'),
                'firmware_version': drive_info.get('firmware_version')
            }
        }

        print(json.dumps(result))
        return 0

    except Exception as e:
        print(json.dumps({
            'success': False,
            'error': str(e)
        }))
        return 1

if __name__ == '__main__':
    sys.exit(main())
