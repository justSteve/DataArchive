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
   * Create or get existing drive record
   */
  upsertDrive(driveInfo: Partial<DriveInfo>): number {
    const serialNumber = driveInfo.serial_number || `UNKNOWN_${Date.now()}`;
    const model = driveInfo.model || 'Unknown Drive';

    // Try to get existing drive by serial number
    const existing = this.db.prepare(`
      SELECT drive_id FROM drives WHERE serial_number = ?
    `).get(serialNumber) as { drive_id: number } | undefined;

    if (existing) {
      // Update last_scanned timestamp
      this.db.prepare(`
        UPDATE drives SET last_scanned = ? WHERE drive_id = ?
      `).run(new Date().toISOString(), existing.drive_id);
      return existing.drive_id;
    }

    // Insert new drive
    const result = this.db.prepare(`
      INSERT INTO drives (
        serial_number, model, manufacturer, size_bytes,
        filesystem, connection_type, media_type, bus_type, first_seen, last_scanned
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(
      serialNumber,
      model,
      driveInfo.manufacturer || null,
      driveInfo.size_bytes || 0,
      driveInfo.filesystem || null,
      driveInfo.connection_type || 'unknown',
      driveInfo.media_type || null,
      driveInfo.bus_type || null,
      new Date().toISOString(),
      new Date().toISOString()
    );

    return result.lastInsertRowid as number;
  }

  /**
   * Create a new scan record with IN_PROGRESS status
   */
  createScan(driveId: number, mountPoint: string): number {
    const result = this.db.prepare(`
      INSERT INTO scans (drive_id, scan_start, mount_point, status)
      VALUES (?, ?, ?, 'IN_PROGRESS')
    `).run(driveId, new Date().toISOString(), mountPoint);

    return result.lastInsertRowid as number;
  }

  /**
   * Update scan status to CANCELLED
   */
  cancelScan(scanId: number): void {
    this.db.prepare(`
      UPDATE scans
      SET status = 'CANCELLED', scan_end = ?
      WHERE scan_id = ?
    `).run(new Date().toISOString(), scanId);
  }

  /**
   * Close database connection
   */
  close(): void {
    this.db.close();
  }
}
