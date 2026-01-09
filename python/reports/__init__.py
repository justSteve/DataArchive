"""
DataArchive v2 Report Generation Module

Generates Claude-friendly markdown reports for each inspection pass.
"""

from .inspection_report import (
    InspectionReportGenerator,
    generate_inspection_report
)

__all__ = [
    'InspectionReportGenerator',
    'generate_inspection_report',
]
