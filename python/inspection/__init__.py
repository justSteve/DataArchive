"""
DataArchive v2 Multi-Pass Inspection Module

Provides the four-pass inspection workflow:
- Pass 1: Drive Health (chkdsk, SMART)
- Pass 2: OS Detection (registry-based)
- Pass 3: Metadata Capture (files, folders)
- Pass 4: Interactive Review (reports, decisions)
"""

# Pass 1: Drive Health Inspector (implemented)
from .pass1_health import DriveHealthInspector, HealthReport, run_health_inspection

# Pass 2: Enhanced OS Detection (implemented)
from .pass2_os import EnhancedOSDetector, OSReport, run_os_inspection

# Passes 3-4 will be imported as they are implemented
# from .pass3_metadata import MetadataCapture
# from .pass4_review import InteractiveReview

__all__ = [
    # Pass 1
    'DriveHealthInspector',
    'HealthReport',
    'run_health_inspection',
    # Pass 2
    'EnhancedOSDetector',
    'OSReport',
    'run_os_inspection',
    # Future passes:
    # 'MetadataCapture',
    # 'InteractiveReview'
]
