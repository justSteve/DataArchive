#!/usr/bin/env python
"""Run multi-pass inspection on a drive."""
import sys
import os
import json

# Add python directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'python'))

from inspection import (
    run_health_inspection,
    run_os_inspection,
    run_metadata_inspection,
    run_review_inspection
)

def main():
    if len(sys.argv) < 3:
        print("Usage: python run_inspection.py <drive_path> <pass_number>")
        print("  pass_number: 1=health, 2=os, 3=metadata, 4=review")
        sys.exit(1)

    drive_path = sys.argv[1]
    pass_num = int(sys.argv[2])

    if pass_num == 1:
        result = run_health_inspection(drive_path, json_output=True)
    elif pass_num == 2:
        result = run_os_inspection(drive_path, json_output=True)
    elif pass_num == 3:
        result = run_metadata_inspection(drive_path, json_output=True)
    elif pass_num == 4:
        result = run_review_inspection(drive_path, json_output=True)
    else:
        print(f"Invalid pass number: {pass_num}")
        sys.exit(1)

    print(json.dumps(result, indent=2, default=str))

if __name__ == '__main__':
    main()
