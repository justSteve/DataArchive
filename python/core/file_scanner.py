"""
File system scanner
"""

import os
from pathlib import Path
from datetime import datetime
from typing import Iterator, Dict, Any
from tqdm import tqdm

from .logger import get_logger

logger = get_logger(__name__)


class FileScanner:
    """Scan file systems and catalog files"""

    # Windows system directories to skip on boot drives (reduced list)
    WINDOWS_BOOT_DIRS = [
        'Windows', 'Program Files', 'Program Files (x86)'
    ]

    # Always skip these directories (on any drive)
    ALWAYS_SKIP_DIRS = [
        '$RECYCLE.BIN', 'System Volume Information', '$Windows.~BT',
        'Windows.old', '.Trash', '.cache', 'Config.Msi', 'Recovery',
        '$WinREAgent'
    ]

    # System files to skip
    SYSTEM_FILES = [
        'pagefile.sys', 'hiberfil.sys', 'swapfile.sys',
        'bootmgr', 'BOOTNXT', 'BOOTSECT.BAK', '$UPG$PBR.MARKER'
    ]

    def __init__(self, drive_path: str, is_windows_boot: bool = False,
                 enable_priority_filtering: bool = True):
        self.drive_path = Path(drive_path)
        self.is_windows_boot = is_windows_boot
        self.enable_priority_filtering = enable_priority_filtering
        self.skipped_count = 0
        self.error_count = 0
        self.priority_stats = {'high': 0, 'medium': 0, 'low': 0, 'skip': 0}
        logger.info(f"FileScanner initialized for: {drive_path} (Windows boot: {is_windows_boot}, priority filtering: {enable_priority_filtering})")
    
    def count_files(self) -> int:
        """Count total files (for progress bar)"""
        logger.info("Counting files...")
        count = 0
        
        try:
            for root, dirs, files in os.walk(self.drive_path):
                # Skip problematic directories
                dirs[:] = [d for d in dirs if not self._should_skip_directory(d)]
                count += len(files)
        except Exception as e:
            logger.error(f"Error counting files: {e}")
            return 0
        
        logger.info(f"Found approximately {count:,} files")
        return count
    
    def scan(self, show_progress: bool = True, enable_hashing: bool = False,
             min_hash_size: int = 1024) -> Iterator[Dict[str, Any]]:
        """
        Scan drive and yield file information with optional inline hashing

        Args:
            show_progress: Display progress bar
            enable_hashing: Compute quick hash for each file during scan
            min_hash_size: Minimum file size for hashing (bytes)

        Yields:
            Dict with file metadata: path, size, dates, extension, hash (optional)
        """
        logger.info(f"Starting file scan of {self.drive_path} (hashing: {enable_hashing})")

        # Import utilities if needed
        if enable_hashing:
            from utils.hash_utils import compute_quick_hash
        if self.enable_priority_filtering:
            from utils.file_priority import classify_file_priority

        # Count files for progress bar
        pbar = None
        if show_progress:
            total_files = self.count_files()
            pbar = tqdm(total=total_files, unit='files', desc='Scanning')

        file_count = 0

        try:
            for root, dirs, files in os.walk(self.drive_path):
                # Get relative path for subdirectory filtering
                root_path = Path(root)
                try:
                    rel_root = root_path.relative_to(self.drive_path)
                except ValueError:
                    rel_root = root_path

                # Filter out directories to skip (context-aware)
                dirs[:] = [d for d in dirs if not self._should_skip_directory(d, str(rel_root))]

                for filename in files:
                    # Skip system files
                    if self._should_skip_file(filename):
                        if pbar:
                            pbar.update(1)
                        continue

                    filepath = os.path.join(root, filename)

                    try:
                        file_info = self._get_file_info(filepath)
                        if file_info:
                            # Classify file priority
                            if self.enable_priority_filtering:
                                priority = classify_file_priority(file_info['path'], file_info['size_bytes'])
                                file_info['priority'] = priority
                                self.priority_stats[priority] += 1

                                # Skip files marked for skipping
                                if priority == 'skip':
                                    self.skipped_count += 1
                                    if pbar:
                                        pbar.update(1)
                                    continue

                            # Inline hash computation
                            if enable_hashing and file_info['size_bytes'] >= min_hash_size:
                                quick_hash, error = compute_quick_hash(filepath)
                                if quick_hash:
                                    file_info['quick_hash'] = quick_hash
                                elif error:
                                    logger.debug(f"Hash error for {filename}: {error}")

                            yield file_info
                            file_count += 1
                        else:
                            # File was inaccessible or had issues
                            self.error_count += 1

                        if pbar:
                            pbar.update(1)

                    except (PermissionError, OSError):
                        self.error_count += 1
                        if pbar:
                            pbar.update(1)
                        continue

        except KeyboardInterrupt:
            logger.warning("Scan interrupted by user")
            raise
        finally:
            if pbar:
                pbar.close()

        # Build summary message
        summary = f"Scan complete: {file_count:,} files processed, " \
                  f"{self.error_count} errors, {self.skipped_count} skipped"

        if self.enable_priority_filtering:
            summary += f" | Priority: high={self.priority_stats['high']:,}, " \
                      f"medium={self.priority_stats['medium']:,}, " \
                      f"low={self.priority_stats['low']:,}"

        logger.info(summary)
    
    def _get_file_info(self, filepath: str) -> Dict[str, Any]:
        """Get metadata for a single file"""
        try:
            stat = os.stat(filepath)
            path_obj = Path(filepath)
            
            # Calculate relative path
            try:
                rel_path = path_obj.relative_to(self.drive_path)
            except ValueError:
                rel_path = path_obj
            
            return {
                'path': str(rel_path),
                'size_bytes': stat.st_size,
                'modified_date': datetime.fromtimestamp(stat.st_mtime),
                'created_date': datetime.fromtimestamp(stat.st_ctime),
                'accessed_date': datetime.fromtimestamp(stat.st_atime),
                'extension': path_obj.suffix.lower(),
                'is_hidden': path_obj.name.startswith('.'),
                'is_system': False  # Would need platform-specific check
            }
        except (PermissionError, OSError) as e:
            # Common in WSL for Windows system files (pagefile.sys, .edb, etc.)
            # Log at debug level to avoid spam - these are expected
            logger.debug(f"Skipped inaccessible file {filepath}: {e}")
            return None
        except Exception as e:
            # Unexpected errors should still be logged
            logger.warning(f"Unexpected error for {filepath}: {e}")
            return None
    
    def _should_skip_directory(self, dirname: str, parent_path: str = '') -> bool:
        """
        Check if directory should be skipped (context-aware filtering)

        Args:
            dirname: Directory name
            parent_path: Parent path (relative to drive root) for context
        """
        # Always skip these directories
        for pattern in self.ALWAYS_SKIP_DIRS:
            if pattern.lower() == dirname.lower():
                logger.debug(f"Skipping always-skip directory: {dirname}")
                self.skipped_count += 1
                return True

        # Skip Windows system directories on boot drives (top-level only)
        if self.is_windows_boot and parent_path in ('', '.'):
            for pattern in self.WINDOWS_BOOT_DIRS:
                if pattern.lower() == dirname.lower():
                    logger.info(f"Skipping Windows boot directory: {dirname}")
                    self.skipped_count += 1
                    return True

        # Smart subdirectory filtering (cache, temp, logs, node_modules)
        if self.enable_priority_filtering:
            skip_subdirs = [
                'cache', 'Cache', 'CACHE',
                'temp', 'Temp', 'tmp',
                'logs', 'Logs',
                'node_modules',
                '__pycache__',
                '.git', '.svn',
                'venv', '.venv',
            ]
            if dirname in skip_subdirs:
                logger.debug(f"Skipping subdirectory: {parent_path}/{dirname}")
                self.skipped_count += 1
                return True

            # Skip browser cache directories
            if 'Cache' in dirname and ('Chrome' in parent_path or 'Firefox' in parent_path):
                logger.debug(f"Skipping browser cache: {parent_path}/{dirname}")
                self.skipped_count += 1
                return True

        return False

    def _should_skip_file(self, filename: str) -> bool:
        """Check if file should be skipped"""
        for sys_file in self.SYSTEM_FILES:
            if sys_file.lower() == filename.lower():
                logger.debug(f"Skipping system file: {filename}")
                return True
        return False
    
    def get_statistics(self, scan_id: int, database) -> Dict[str, Any]:
        """Calculate scan statistics from database"""
        with database.get_connection() as conn:
            cursor = conn.execute("""
                SELECT 
                    COUNT(*) as total_files,
                    SUM(size_bytes) as total_size,
                    MIN(modified_date) as oldest_file,
                    MAX(modified_date) as newest_file,
                    MAX(size_bytes) as largest_file,
                    extension,
                    COUNT(*) as ext_count
                FROM files
                WHERE scan_id = ?
                GROUP BY extension
                ORDER BY ext_count DESC
                LIMIT 1
            """, (scan_id,))
            
            row = cursor.fetchone()
            if row:
                return {
                    'total_files': row['total_files'],
                    'total_size': row['total_size'],
                    'oldest_file_date': row['oldest_file'],
                    'newest_file_date': row['newest_file'],
                    'largest_file_size': row['largest_file'],
                    'most_common_extension': row['extension']
                }
        
        return {}
