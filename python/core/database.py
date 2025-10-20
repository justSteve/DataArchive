"""
Database interface for Data Archive System
"""

import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Any
from contextlib import contextmanager

from .logger import get_logger

logger = get_logger(__name__)


class Database:
    """SQLite database interface"""
    
    def __init__(self, db_path: str = "output/archive.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(exist_ok=True)
        self._init_schema()
        logger.info(f"Database initialized: {self.db_path}")
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()
    
    def _init_schema(self):
        """Initialize database schema"""
        with self.get_connection() as conn:
            conn.executescript("""
                -- Physical drives
                CREATE TABLE IF NOT EXISTS drives (
                    drive_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    serial_number TEXT UNIQUE,
                    model TEXT,
                    manufacturer TEXT,
                    size_bytes INTEGER,
                    filesystem TEXT,
                    partition_scheme TEXT,
                    label TEXT,
                    connection_type TEXT,
                    firmware_version TEXT,
                    media_type TEXT,
                    bus_type TEXT,
                    notes TEXT,
                    first_seen TIMESTAMP,
                    last_scanned TIMESTAMP
                );
                
                -- Scan sessions
                CREATE TABLE IF NOT EXISTS scans (
                    scan_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    drive_id INTEGER,
                    scan_start TIMESTAMP,
                    scan_end TIMESTAMP,
                    mount_point TEXT,
                    file_count INTEGER,
                    total_size_bytes INTEGER,
                    status TEXT,
                    FOREIGN KEY (drive_id) REFERENCES drives(drive_id)
                );
                
                -- Operating system detection
                CREATE TABLE IF NOT EXISTS os_info (
                    scan_id INTEGER PRIMARY KEY,
                    os_type TEXT,
                    os_name TEXT,
                    version TEXT,
                    build_number TEXT,
                    edition TEXT,
                    install_date TEXT,
                    boot_capable BOOLEAN,
                    detection_method TEXT,
                    confidence TEXT,
                    FOREIGN KEY (scan_id) REFERENCES scans(scan_id)
                );
                
                -- Files on drives
                CREATE TABLE IF NOT EXISTS files (
                    file_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_id INTEGER,
                    path TEXT,
                    size_bytes INTEGER,
                    modified_date TIMESTAMP,
                    created_date TIMESTAMP,
                    accessed_date TIMESTAMP,
                    extension TEXT,
                    is_hidden BOOLEAN,
                    is_system BOOLEAN,
                    FOREIGN KEY (scan_id) REFERENCES scans(scan_id)
                );
                
                -- Scan statistics
                CREATE TABLE IF NOT EXISTS scan_statistics (
                    scan_id INTEGER PRIMARY KEY,
                    total_files INTEGER,
                    total_folders INTEGER,
                    oldest_file_date TIMESTAMP,
                    newest_file_date TIMESTAMP,
                    largest_file_size INTEGER,
                    most_common_extension TEXT,
                    extension_counts TEXT,
                    FOREIGN KEY (scan_id) REFERENCES scans(scan_id)
                );
                
                -- Create indexes
                CREATE INDEX IF NOT EXISTS idx_files_extension ON files(extension);
                CREATE INDEX IF NOT EXISTS idx_files_scan_path ON files(scan_id, path);
                CREATE INDEX IF NOT EXISTS idx_files_size ON files(size_bytes);
                CREATE INDEX IF NOT EXISTS idx_files_modified ON files(modified_date);
                CREATE INDEX IF NOT EXISTS idx_scans_drive ON scans(drive_id);
            """)
        logger.info("Database schema initialized")
    
    def insert_drive(self, drive_info: Dict[str, Any]) -> int:
        """Insert or update drive information"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO drives (
                    serial_number, model, manufacturer, size_bytes,
                    filesystem, partition_scheme, label, connection_type,
                    firmware_version, media_type, bus_type, notes,
                    first_seen, last_scanned
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(serial_number) DO UPDATE SET
                    last_scanned = ?,
                    firmware_version = COALESCE(excluded.firmware_version, firmware_version),
                    media_type = COALESCE(excluded.media_type, media_type),
                    bus_type = COALESCE(excluded.bus_type, bus_type),
                    notes = COALESCE(excluded.notes, notes)
            """, (
                drive_info['serial_number'],
                drive_info.get('model'),
                drive_info.get('manufacturer'),
                drive_info.get('size_bytes'),
                drive_info.get('filesystem'),
                drive_info.get('partition_scheme'),
                drive_info.get('label'),
                drive_info.get('connection_type'),
                drive_info.get('firmware_version'),
                drive_info.get('media_type'),
                drive_info.get('bus_type'),
                drive_info.get('notes'),
                datetime.now(),
                datetime.now(),
                datetime.now()
            ))
            
            # Get drive_id
            cursor = conn.execute(
                "SELECT drive_id FROM drives WHERE serial_number = ?",
                (drive_info['serial_number'],)
            )
            drive_id = cursor.fetchone()[0]
            logger.debug(f"Inserted/updated drive: {drive_id}")
            return drive_id
    
    def start_scan(self, drive_id: int, mount_point: str) -> int:
        """Start a new scan session"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO scans (drive_id, scan_start, mount_point, status)
                VALUES (?, ?, ?, 'IN_PROGRESS')
            """, (drive_id, datetime.now(), mount_point))
            scan_id = cursor.lastrowid
            logger.info(f"Started scan session: {scan_id}")
            return scan_id
    
    def complete_scan(self, scan_id: int, file_count: int, total_size: int):
        """Mark scan as complete"""
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE scans 
                SET scan_end = ?, file_count = ?, total_size_bytes = ?, status = 'COMPLETE'
                WHERE scan_id = ?
            """, (datetime.now(), file_count, total_size, scan_id))
            logger.info(f"Completed scan: {scan_id} ({file_count} files, {total_size} bytes)")
    
    def insert_os_info(self, scan_id: int, os_info: Dict[str, Any]):
        """Insert OS detection results"""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO os_info (
                    scan_id, os_type, os_name, version, build_number,
                    edition, install_date, boot_capable, detection_method, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                scan_id,
                os_info.get('os_type'),
                os_info.get('os_name'),
                os_info.get('version'),
                os_info.get('build_number'),
                os_info.get('edition'),
                os_info.get('install_date'),
                os_info.get('boot_capable', False),
                os_info.get('detection_method'),
                os_info.get('confidence')
            ))
            logger.debug(f"Inserted OS info for scan: {scan_id}")
    
    def insert_files_batch(self, scan_id: int, files: List[Dict[str, Any]]):
        """Batch insert files"""
        with self.get_connection() as conn:
            conn.executemany("""
                INSERT INTO files (
                    scan_id, path, size_bytes, modified_date, created_date,
                    accessed_date, extension, is_hidden, is_system
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                (
                    scan_id,
                    f['path'],
                    f['size_bytes'],
                    f['modified_date'],
                    f['created_date'],
                    f.get('accessed_date'),
                    f['extension'],
                    f.get('is_hidden', False),
                    f.get('is_system', False)
                ) for f in files
            ])
            logger.debug(f"Inserted {len(files)} files for scan: {scan_id}")
    
    def get_scan_info(self, scan_id: int) -> Optional[Dict]:
        """Get scan information"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT s.*, d.model, d.serial_number
                FROM scans s
                JOIN drives d ON s.drive_id = d.drive_id
                WHERE s.scan_id = ?
            """, (scan_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_file_tree(self, scan_id: int, max_depth: int = 3) -> Dict:
        """Get directory tree for scan"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT path, size_bytes 
                FROM files 
                WHERE scan_id = ?
            """, (scan_id,))
            
            # Build tree structure
            tree = {}
            for row in cursor:
                path_parts = row['path'].split('/')
                if len(path_parts) > max_depth:
                    continue
                    
                current = tree
                for i, part in enumerate(path_parts[:-1]):
                    if part not in current:
                        current[part] = {
                            'type': 'dir',
                            'size': 0,
                            'file_count': 0,
                            'children': {}
                        }
                    current[part]['size'] += row['size_bytes']
                    current[part]['file_count'] += 1
                    current = current[part]['children']
            
            return tree
