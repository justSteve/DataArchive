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
    
    def __init__(self, drive_path: str):
        self.drive_path = Path(drive_path)
        self.skipped_count = 0
        self.error_count = 0
        logger.info(f"FileScanner initialized for: {drive_path}")
    
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
    
    def scan(self, show_progress: bool = True) -> Iterator[Dict[str, Any]]:
        """
        Scan drive and yield file information
        
        Yields:
            Dict with file metadata: path, size, dates, extension, etc.
        """
        logger.info(f"Starting file scan of {self.drive_path}")
        
        # Count files for progress bar
        if show_progress:
            total_files = self.count_files()
            pbar = tqdm(total=total_files, unit='files', desc='Scanning')
        
        file_count = 0
        
        try:
            for root, dirs, files in os.walk(self.drive_path):
                # Filter out directories to skip
                dirs[:] = [d for d in dirs if not self._should_skip_directory(d)]
                
                for filename in files:
                    filepath = os.path.join(root, filename)
                    
                    try:
                        file_info = self._get_file_info(filepath)
                        if file_info:
                            yield file_info
                            file_count += 1
                        else:
                            # File was inaccessible or had issues
                            self.error_count += 1
                        
                        if show_progress:
                            pbar.update(1)
                                
                    except (PermissionError, OSError) as e:
                        self.error_count += 1
                        if show_progress:
                            pbar.update(1)
                        continue
                    
        except KeyboardInterrupt:
            logger.warning("Scan interrupted by user")
            raise
        finally:
            if show_progress:
                pbar.close()
        
        logger.info(
            f"Scan complete: {file_count:,} files processed, "
            f"{self.error_count} errors, {self.skipped_count} skipped"
        )
    
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
    
    def _should_skip_directory(self, dirname: str) -> bool:
        """Check if directory should be skipped"""
        skip_patterns = [
            '$RECYCLE.BIN',
            'System Volume Information',
            '$Windows.~BT',
            'Windows.old',
            '.Trash',
            '.cache',
        ]
        
        for pattern in skip_patterns:
            if pattern.lower() in dirname.lower():
                self.skipped_count += 1
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
