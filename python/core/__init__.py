"""
Core modules for DataArchive

Contains:
- database.py: SQLite database interface
- drive_manager.py: Drive detection and hardware identification
- drive_validator.py: Path validation
- file_scanner.py: Recursive file cataloging
- logger.py: Logging configuration
- os_detector.py: Operating system detection
"""

from .logger import get_logger, Logger
from .database import Database
from .drive_manager import DriveManager
from .drive_validator import DriveValidator
from .os_detector import OSDetector
from .file_scanner import FileScanner

__all__ = [
    'get_logger',
    'Logger',
    'Database',
    'DriveManager',
    'DriveValidator',
    'OSDetector',
    'FileScanner'
]
