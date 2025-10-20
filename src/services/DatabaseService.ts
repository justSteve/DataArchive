/**
 * TypeScript interface to SQLite database
 * Queries the same database that Python writes to
 */

import Database from 'better-sqlite3';
import path from 'path';
import { ScanInfo, FileInfo, DriveInfo, OSInfo } from '../domain/models/types';

export class DatabaseService {
  private db: Database.Database;

  constructor(dbPath: string = './output/archive.db') {
    const fullPath = path.resolve(dbPath);
    this.db = new Database(fullPath);
  }

  /**
   * Get all scans ordered by most recent
   */
  getScans(limit: number = 100): ScanInfo[] {
    const stmt = this.db.prepare(`
      SELECT
        s.scan_id,
        s.drive_id,
        s.scan_start,
        s.scan_end,
        s.mount_point,
        s.file_count,
        s.total_size_bytes,
        s.status,
        d.model,
        d.serial_number
      FROM scans s
      JOIN drives d ON s.drive_id = d.drive_id
      ORDER BY s.scan_start DESC
      LIMIT ?
    `);
    return stmt.all(limit) as ScanInfo[];
  }

  /**
   * Get a specific scan by ID
   */
  getScan(scanId: number): ScanInfo | undefined {
    const stmt = this.db.prepare(`
      SELECT
        s.scan_id,
        s.drive_id,
        s.scan_start,
        s.scan_end,
        s.mount_point,
        s.file_count,
        s.total_size_bytes,
        s.status,
        d.model,
        d.serial_number
      FROM scans s
      JOIN drives d ON s.drive_id = d.drive_id
      WHERE s.scan_id = ?
    `);
    return stmt.get(scanId) as ScanInfo | undefined;
  }

  /**
   * Get files for a scan
   */
  getFiles(scanId: number, limit: number = 1000, offset: number = 0): FileInfo[] {
    const stmt = this.db.prepare(`
      SELECT
        file_id,
        scan_id,
        path,
        size_bytes,
        modified_date,
        created_date,
        accessed_date,
        extension,
        is_hidden,
        is_system
      FROM files
      WHERE scan_id = ?
      ORDER BY path
      LIMIT ? OFFSET ?
    `);
    return stmt.all(scanId, limit, offset) as FileInfo[];
  }

  /**
   * Get file count for a scan
   */
  getFileCount(scanId: number): number {
    const stmt = this.db.prepare(`
      SELECT COUNT(*) as count
      FROM files
      WHERE scan_id = ?
    `);
    const result = stmt.get(scanId) as { count: number };
    return result.count;
  }

  /**
   * Get OS information for a scan
   */
  getOSInfo(scanId: number): OSInfo | undefined {
    const stmt = this.db.prepare(`
      SELECT
        os_type,
        os_name,
        version,
        build_number,
        edition,
        install_date,
        boot_capable,
        detection_method,
        confidence
      FROM os_info
      WHERE scan_id = ?
    `);
    return stmt.get(scanId) as OSInfo | undefined;
  }

  /**
   * Get all drives
   */
  getDrives(): DriveInfo[] {
    const stmt = this.db.prepare(`
      SELECT
        serial_number,
        model,
        manufacturer,
        size_bytes,
        filesystem,
        connection_type,
        media_type,
        bus_type,
        firmware_version
      FROM drives
      ORDER BY last_scanned DESC
    `);
    return stmt.all() as DriveInfo[];
  }

  /**
   * Search files by extension
   */
  searchByExtension(scanId: number, extension: string, limit: number = 100): FileInfo[] {
    const stmt = this.db.prepare(`
      SELECT
        file_id,
        scan_id,
        path,
        size_bytes,
        modified_date,
        created_date,
        accessed_date,
        extension,
        is_hidden,
        is_system
      FROM files
      WHERE scan_id = ? AND extension = ?
      ORDER BY path
      LIMIT ?
    `);
    return stmt.all(scanId, extension, limit) as FileInfo[];
  }

  /**
   * Close database connection
   */
  close(): void {
    this.db.close();
  }
}
