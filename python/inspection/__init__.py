"""
DataArchive v2 Multi-Pass Inspection Module

Provides the four-pass inspection workflow:
- Pass 1: Drive Health (chkdsk, SMART)
- Pass 2: OS Detection (registry-based)
- Pass 3: Metadata Capture (files, folders, duplicate detection)
- Pass 4: Interactive Review (reports, decisions)
"""

# Pass 1: Drive Health Inspector
from .pass1_health import DriveHealthInspector, HealthReport, run_health_inspection

# Pass 2: Enhanced OS Detection
from .pass2_os import EnhancedOSDetector, OSReport, run_os_inspection

# Pass 3: Metadata Capture with Duplicate Detection
from .pass3_metadata import (
    MetadataCapture,
    MetadataReport,
    DuplicateGroup,
    DuplicateInfo,
    run_metadata_inspection
)

# Pass 4: Interactive Review
from .pass4_review import (
    InteractiveReview,
    ReviewReport,
    DecisionPoint,
    DuplicateHandling,
    OSPreservation,
    FilterAction,
    run_review_inspection
)

__all__ = [
    # Pass 1
    'DriveHealthInspector',
    'HealthReport',
    'run_health_inspection',
    # Pass 2
    'EnhancedOSDetector',
    'OSReport',
    'run_os_inspection',
    # Pass 3
    'MetadataCapture',
    'MetadataReport',
    'DuplicateGroup',
    'DuplicateInfo',
    'run_metadata_inspection',
    # Pass 4
    'InteractiveReview',
    'ReviewReport',
    'DecisionPoint',
    'DuplicateHandling',
    'OSPreservation',
    'FilterAction',
    'run_review_inspection',
]
