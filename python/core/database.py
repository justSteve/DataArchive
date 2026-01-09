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
                
                -- =============================================
                -- V2 INSPECTION TABLES (Multi-pass workflow)
                -- =============================================

                -- Inspection sessions (multi-pass workflow)
                CREATE TABLE IF NOT EXISTS inspection_sessions (
                    session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    drive_id INTEGER,
                    started_at TIMESTAMP NOT NULL,
                    completed_at TIMESTAMP,
                    status TEXT NOT NULL DEFAULT 'active',
                    current_pass INTEGER DEFAULT 1,
                    beads_issue_id TEXT,
                    FOREIGN KEY (drive_id) REFERENCES drives(drive_id)
                );

                -- Per-pass results
                CREATE TABLE IF NOT EXISTS inspection_passes (
                    pass_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    pass_number INTEGER NOT NULL,
                    pass_name TEXT,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    status TEXT NOT NULL DEFAULT 'pending',
                    report_json TEXT,
                    error_message TEXT,
                    FOREIGN KEY (session_id) REFERENCES inspection_sessions(session_id)
                );

                -- User/Claude decisions from inspection review
                CREATE TABLE IF NOT EXISTS inspection_decisions (
                    decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    decision_type TEXT NOT NULL,
                    decision_key TEXT NOT NULL,
                    decision_value TEXT NOT NULL,
                    description TEXT,
                    decided_at TIMESTAMP NOT NULL,
                    decided_by TEXT DEFAULT 'user',
                    FOREIGN KEY (session_id) REFERENCES inspection_sessions(session_id)
                );

                -- File hashes for duplicate detection
                CREATE TABLE IF NOT EXISTS file_hashes (
                    hash_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_id INTEGER NOT NULL,
                    file_id INTEGER NOT NULL,
                    hash_type TEXT NOT NULL,
                    hash_value TEXT NOT NULL,
                    computed_at TIMESTAMP NOT NULL,
                    FOREIGN KEY (scan_id) REFERENCES scans(scan_id),
                    FOREIGN KEY (file_id) REFERENCES files(file_id)
                );

                -- Duplicate file groups
                CREATE TABLE IF NOT EXISTS duplicate_groups (
                    group_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hash_value TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    file_count INTEGER DEFAULT 0,
                    total_wasted_bytes INTEGER DEFAULT 0,
                    created_at TIMESTAMP NOT NULL,
                    status TEXT DEFAULT 'unresolved'
                );

                -- Members of duplicate groups
                CREATE TABLE IF NOT EXISTS duplicate_members (
                    member_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER NOT NULL,
                    file_id INTEGER NOT NULL,
                    scan_id INTEGER NOT NULL,
                    is_primary BOOLEAN DEFAULT FALSE,
                    FOREIGN KEY (group_id) REFERENCES duplicate_groups(group_id),
                    FOREIGN KEY (file_id) REFERENCES files(file_id),
                    FOREIGN KEY (scan_id) REFERENCES scans(scan_id)
                );

                -- Create indexes (v1)
                CREATE INDEX IF NOT EXISTS idx_files_extension ON files(extension);
                CREATE INDEX IF NOT EXISTS idx_files_scan_path ON files(scan_id, path);
                CREATE INDEX IF NOT EXISTS idx_files_size ON files(size_bytes);
                CREATE INDEX IF NOT EXISTS idx_files_modified ON files(modified_date);
                CREATE INDEX IF NOT EXISTS idx_scans_drive ON scans(drive_id);

                -- Create indexes (v2 inspection)
                CREATE INDEX IF NOT EXISTS idx_sessions_drive ON inspection_sessions(drive_id);
                CREATE INDEX IF NOT EXISTS idx_sessions_status ON inspection_sessions(status);
                CREATE INDEX IF NOT EXISTS idx_passes_session ON inspection_passes(session_id);
                CREATE INDEX IF NOT EXISTS idx_passes_status ON inspection_passes(status);
                CREATE INDEX IF NOT EXISTS idx_decisions_session ON inspection_decisions(session_id);
                CREATE INDEX IF NOT EXISTS idx_decisions_type ON inspection_decisions(decision_type);
                CREATE INDEX IF NOT EXISTS idx_hashes_value ON file_hashes(hash_value);
                CREATE INDEX IF NOT EXISTS idx_hashes_file ON file_hashes(file_id);
                CREATE INDEX IF NOT EXISTS idx_hashes_scan ON file_hashes(scan_id);
                CREATE INDEX IF NOT EXISTS idx_dup_groups_hash ON duplicate_groups(hash_value);
                CREATE INDEX IF NOT EXISTS idx_dup_members_group ON duplicate_members(group_id);
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

    # =========================================
    # V2 INSPECTION METHODS
    # =========================================

    def start_inspection(self, drive_id: int, beads_issue_id: Optional[str] = None) -> int:
        """Start a new inspection session"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO inspection_sessions
                (drive_id, started_at, status, current_pass, beads_issue_id)
                VALUES (?, ?, 'active', 1, ?)
            """, (drive_id, datetime.now(), beads_issue_id))
            session_id = cursor.lastrowid

            # Create placeholder pass records for all 4 passes
            for pass_num, pass_name in [(1, 'health'), (2, 'os_detection'),
                                         (3, 'metadata'), (4, 'review')]:
                conn.execute("""
                    INSERT INTO inspection_passes
                    (session_id, pass_number, pass_name, status)
                    VALUES (?, ?, ?, 'pending')
                """, (session_id, pass_num, pass_name))

            logger.info(f"Started inspection session: {session_id}")
            return session_id

    def get_inspection(self, session_id: int) -> Optional[Dict]:
        """Get inspection session with all passes"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT s.*, d.model, d.serial_number
                FROM inspection_sessions s
                LEFT JOIN drives d ON s.drive_id = d.drive_id
                WHERE s.session_id = ?
            """, (session_id,))
            session = cursor.fetchone()
            if not session:
                return None

            result = dict(session)

            # Get passes
            cursor = conn.execute("""
                SELECT * FROM inspection_passes
                WHERE session_id = ?
                ORDER BY pass_number
            """, (session_id,))
            result['passes'] = [dict(row) for row in cursor.fetchall()]

            return result

    def start_pass(self, session_id: int, pass_number: int) -> bool:
        """Mark a pass as started"""
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE inspection_passes
                SET status = 'running', started_at = ?
                WHERE session_id = ? AND pass_number = ?
            """, (datetime.now(), session_id, pass_number))

            conn.execute("""
                UPDATE inspection_sessions
                SET current_pass = ?
                WHERE session_id = ?
            """, (pass_number, session_id))

            logger.info(f"Started pass {pass_number} for session {session_id}")
            return True

    def complete_pass(self, session_id: int, pass_number: int,
                      report_json: Optional[str] = None,
                      error_message: Optional[str] = None) -> bool:
        """Mark a pass as completed"""
        status = 'failed' if error_message else 'completed'
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE inspection_passes
                SET status = ?, completed_at = ?, report_json = ?, error_message = ?
                WHERE session_id = ? AND pass_number = ?
            """, (status, datetime.now(), report_json, error_message,
                  session_id, pass_number))

            logger.info(f"Completed pass {pass_number} for session {session_id}: {status}")
            return True

    def skip_pass(self, session_id: int, pass_number: int, reason: str) -> bool:
        """Skip a pass with reason"""
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE inspection_passes
                SET status = 'skipped', completed_at = ?, error_message = ?
                WHERE session_id = ? AND pass_number = ?
            """, (datetime.now(), reason, session_id, pass_number))

            logger.info(f"Skipped pass {pass_number} for session {session_id}: {reason}")
            return True

    def complete_inspection(self, session_id: int, status: str = 'completed') -> bool:
        """Mark inspection session as complete"""
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE inspection_sessions
                SET status = ?, completed_at = ?
                WHERE session_id = ?
            """, (status, datetime.now(), session_id))

            logger.info(f"Completed inspection session {session_id}: {status}")
            return True

    def record_decision(self, session_id: int, decision_type: str,
                        decision_key: str, decision_value: str,
                        description: Optional[str] = None,
                        decided_by: str = 'user') -> int:
        """Record an inspection decision"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO inspection_decisions
                (session_id, decision_type, decision_key, decision_value,
                 description, decided_at, decided_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (session_id, decision_type, decision_key, decision_value,
                  description, datetime.now(), decided_by))

            decision_id = cursor.lastrowid
            logger.debug(f"Recorded decision {decision_id}: {decision_type}={decision_value}")
            return decision_id

    def get_decisions(self, session_id: int) -> List[Dict]:
        """Get all decisions for an inspection session"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM inspection_decisions
                WHERE session_id = ?
                ORDER BY decided_at
            """, (session_id,))
            return [dict(row) for row in cursor.fetchall()]

    def insert_file_hash(self, scan_id: int, file_id: int,
                         hash_type: str, hash_value: str) -> int:
        """Insert a file hash for duplicate detection"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO file_hashes
                (scan_id, file_id, hash_type, hash_value, computed_at)
                VALUES (?, ?, ?, ?, ?)
            """, (scan_id, file_id, hash_type, hash_value, datetime.now()))
            return cursor.lastrowid

    def insert_file_hashes_batch(self, hashes: List[Dict[str, Any]]) -> int:
        """Batch insert file hashes"""
        with self.get_connection() as conn:
            conn.executemany("""
                INSERT INTO file_hashes
                (scan_id, file_id, hash_type, hash_value, computed_at)
                VALUES (?, ?, ?, ?, ?)
            """, [
                (h['scan_id'], h['file_id'], h['hash_type'],
                 h['hash_value'], datetime.now())
                for h in hashes
            ])
            return len(hashes)

    def find_duplicates_by_hash(self, hash_value: str) -> List[Dict]:
        """Find all files with a specific hash"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT h.*, f.path, f.size_bytes, s.mount_point, d.model
                FROM file_hashes h
                JOIN files f ON h.file_id = f.file_id
                JOIN scans s ON h.scan_id = s.scan_id
                JOIN drives d ON s.drive_id = d.drive_id
                WHERE h.hash_value = ?
            """, (hash_value,))
            return [dict(row) for row in cursor.fetchall()]

    def find_potential_duplicates(self, scan_id: int,
                                   min_size: int = 1024) -> List[Dict]:
        """Find files that might be duplicates based on size and name"""
        with self.get_connection() as conn:
            # Find files in this scan that match size+filename in other scans
            cursor = conn.execute("""
                SELECT
                    f1.file_id as new_file_id,
                    f1.path as new_path,
                    f1.size_bytes,
                    f2.file_id as existing_file_id,
                    f2.path as existing_path,
                    s2.scan_id as existing_scan_id,
                    d2.model as existing_drive
                FROM files f1
                JOIN files f2 ON f1.size_bytes = f2.size_bytes
                    AND f1.size_bytes >= ?
                    AND LOWER(SUBSTR(f1.path, -INSTR(REVERSE(f1.path), '/') + 1)) =
                        LOWER(SUBSTR(f2.path, -INSTR(REVERSE(f2.path), '/') + 1))
                JOIN scans s2 ON f2.scan_id = s2.scan_id
                JOIN drives d2 ON s2.drive_id = d2.drive_id
                WHERE f1.scan_id = ? AND f2.scan_id != ?
                LIMIT 1000
            """, (min_size, scan_id, scan_id))
            return [dict(row) for row in cursor.fetchall()]

    def get_active_inspections(self) -> List[Dict]:
        """Get all active inspection sessions"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT s.*, d.model, d.serial_number
                FROM inspection_sessions s
                LEFT JOIN drives d ON s.drive_id = d.drive_id
                WHERE s.status = 'active'
                ORDER BY s.started_at DESC
            """)
            return [dict(row) for row in cursor.fetchall()]

    def get_inspection_history(self, drive_id: Optional[int] = None,
                                limit: int = 20) -> List[Dict]:
        """Get inspection history, optionally filtered by drive"""
        with self.get_connection() as conn:
            if drive_id:
                cursor = conn.execute("""
                    SELECT s.*, d.model, d.serial_number
                    FROM inspection_sessions s
                    LEFT JOIN drives d ON s.drive_id = d.drive_id
                    WHERE s.drive_id = ?
                    ORDER BY s.started_at DESC
                    LIMIT ?
                """, (drive_id, limit))
            else:
                cursor = conn.execute("""
                    SELECT s.*, d.model, d.serial_number
                    FROM inspection_sessions s
                    LEFT JOIN drives d ON s.drive_id = d.drive_id
                    ORDER BY s.started_at DESC
                    LIMIT ?
                """, (limit,))
            return [dict(row) for row in cursor.fetchall()]
