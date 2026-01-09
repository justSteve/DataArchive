/**
 * TypeScript interface to SQLite database
 * Queries the same database that Python writes to
 *
 * Uses bun:sqlite for Bun runtime compatibility
 */

import { Database } from 'bun:sqlite';
import path from 'path';
import { ScanInfo, FileInfo, DriveInfo, OSInfo } from '../domain/models/types';

export class DatabaseService {
  private db: Database;

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

  // =========================================
  // V2 INSPECTION METHODS
  // =========================================

  /**
   * Get inspections with optional status filter
   */
  getInspections(limit: number = 20, status?: string): any[] {
    let stmt;
    if (status) {
      stmt = this.db.prepare(`
        SELECT s.*, d.model, d.serial_number
        FROM inspection_sessions s
        LEFT JOIN drives d ON s.drive_id = d.drive_id
        WHERE s.status = ?
        ORDER BY s.started_at DESC
        LIMIT ?
      `);
      return stmt.all(status, limit);
    } else {
      stmt = this.db.prepare(`
        SELECT s.*, d.model, d.serial_number
        FROM inspection_sessions s
        LEFT JOIN drives d ON s.drive_id = d.drive_id
        ORDER BY s.started_at DESC
        LIMIT ?
      `);
      return stmt.all(limit);
    }
  }

  /**
   * Get active inspections
   */
  getActiveInspections(): any[] {
    const stmt = this.db.prepare(`
      SELECT s.*, d.model, d.serial_number
      FROM inspection_sessions s
      LEFT JOIN drives d ON s.drive_id = d.drive_id
      WHERE s.status = 'active'
      ORDER BY s.started_at DESC
    `);
    return stmt.all();
  }

  /**
   * Get a specific inspection with passes
   */
  getInspection(sessionId: number): any | undefined {
    const sessionStmt = this.db.prepare(`
      SELECT s.*, d.model, d.serial_number, sc.mount_point
      FROM inspection_sessions s
      LEFT JOIN drives d ON s.drive_id = d.drive_id
      LEFT JOIN scans sc ON sc.drive_id = s.drive_id
      WHERE s.session_id = ?
    `);
    const session = sessionStmt.get(sessionId);

    if (!session) return undefined;

    const passesStmt = this.db.prepare(`
      SELECT * FROM inspection_passes
      WHERE session_id = ?
      ORDER BY pass_number
    `);
    const passes = passesStmt.all(sessionId);

    return {
      ...session,
      passes
    };
  }

  /**
   * Start a new inspection session
   */
  startInspection(driveId: number, beadsIssueId?: string): number {
    const result = this.db.prepare(`
      INSERT INTO inspection_sessions
      (drive_id, started_at, status, current_pass, beads_issue_id)
      VALUES (?, ?, 'active', 1, ?)
    `).run(driveId, new Date().toISOString(), beadsIssueId || null);

    const sessionId = result.lastInsertRowid as number;

    // Create placeholder pass records
    const passNames = ['health', 'os_detection', 'metadata', 'review'];
    for (let i = 0; i < 4; i++) {
      this.db.prepare(`
        INSERT INTO inspection_passes
        (session_id, pass_number, pass_name, status)
        VALUES (?, ?, ?, 'pending')
      `).run(sessionId, i + 1, passNames[i]);
    }

    return sessionId;
  }

  /**
   * Get all passes for an inspection
   */
  getInspectionPasses(sessionId: number): any[] {
    const stmt = this.db.prepare(`
      SELECT * FROM inspection_passes
      WHERE session_id = ?
      ORDER BY pass_number
    `);
    return stmt.all(sessionId);
  }

  /**
   * Get a specific pass
   */
  getInspectionPass(sessionId: number, passNumber: number): any | undefined {
    const stmt = this.db.prepare(`
      SELECT * FROM inspection_passes
      WHERE session_id = ? AND pass_number = ?
    `);
    return stmt.get(sessionId, passNumber);
  }

  /**
   * Mark a pass as started
   */
  startPass(sessionId: number, passNumber: number): void {
    this.db.prepare(`
      UPDATE inspection_passes
      SET status = 'running', started_at = ?
      WHERE session_id = ? AND pass_number = ?
    `).run(new Date().toISOString(), sessionId, passNumber);

    this.db.prepare(`
      UPDATE inspection_sessions
      SET current_pass = ?
      WHERE session_id = ?
    `).run(passNumber, sessionId);
  }

  /**
   * Complete a pass with results
   */
  completePass(sessionId: number, passNumber: number, reportJson?: string, errorMessage?: string): void {
    const status = errorMessage ? 'failed' : 'completed';
    this.db.prepare(`
      UPDATE inspection_passes
      SET status = ?, completed_at = ?, report_json = ?, error_message = ?
      WHERE session_id = ? AND pass_number = ?
    `).run(status, new Date().toISOString(), reportJson || null, errorMessage || null, sessionId, passNumber);
  }

  /**
   * Mark a pass as failed
   */
  failPass(sessionId: number, passNumber: number, errorMessage: string): void {
    this.completePass(sessionId, passNumber, undefined, errorMessage);
  }

  /**
   * Skip a pass
   */
  skipPass(sessionId: number, passNumber: number, reason: string): void {
    this.db.prepare(`
      UPDATE inspection_passes
      SET status = 'skipped', completed_at = ?, error_message = ?
      WHERE session_id = ? AND pass_number = ?
    `).run(new Date().toISOString(), reason, sessionId, passNumber);
  }

  /**
   * Complete an inspection session
   */
  completeInspection(sessionId: number, status: string = 'completed'): void {
    this.db.prepare(`
      UPDATE inspection_sessions
      SET status = ?, completed_at = ?
      WHERE session_id = ?
    `).run(status, new Date().toISOString(), sessionId);
  }

  /**
   * Get decisions for an inspection
   */
  getDecisions(sessionId: number): any[] {
    const stmt = this.db.prepare(`
      SELECT * FROM inspection_decisions
      WHERE session_id = ?
      ORDER BY decided_at
    `);
    return stmt.all(sessionId);
  }

  /**
   * Record a decision
   */
  recordDecision(
    sessionId: number,
    decisionType: string,
    decisionKey: string,
    decisionValue: string,
    description?: string,
    decidedBy: string = 'user'
  ): number {
    const result = this.db.prepare(`
      INSERT INTO inspection_decisions
      (session_id, decision_type, decision_key, decision_value, description, decided_at, decided_by)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `).run(sessionId, decisionType, decisionKey, decisionValue, description || null, new Date().toISOString(), decidedBy);

    return result.lastInsertRowid as number;
  }

  /**
   * Delete a decision
   */
  deleteDecision(sessionId: number, decisionId: number): boolean {
    const result = this.db.prepare(`
      DELETE FROM inspection_decisions
      WHERE session_id = ? AND decision_id = ?
    `).run(sessionId, decisionId);

    return result.changes > 0;
  }

  /**
   * Get duplicate groups for a session (via associated scan)
   */
  getDuplicateGroups(sessionId: number, limit: number = 50): any[] {
    // Get the scan_id associated with this inspection's drive
    const inspection = this.getInspection(sessionId);
    if (!inspection || !inspection.drive_id) {
      return [];
    }

    // Find most recent scan for this drive
    const scan = this.db.prepare(`
      SELECT scan_id FROM scans
      WHERE drive_id = ?
      ORDER BY scan_start DESC
      LIMIT 1
    `).get(inspection.drive_id) as { scan_id: number } | undefined;

    if (!scan) return [];

    // Get duplicate groups
    const groups = this.db.prepare(`
      SELECT
        dg.group_id,
        dg.hash_value,
        dg.file_size,
        dg.file_count,
        dg.total_wasted_bytes,
        dg.status
      FROM duplicate_groups dg
      JOIN duplicate_members dm ON dg.group_id = dm.group_id
      WHERE dm.scan_id = ?
      GROUP BY dg.group_id
      ORDER BY dg.total_wasted_bytes DESC
      LIMIT ?
    `).all(scan.scan_id, limit);

    // Get members for each group
    return groups.map((group: any) => {
      const members = this.db.prepare(`
        SELECT
          dm.member_id,
          dm.is_primary,
          f.path,
          f.size_bytes,
          f.modified_date
        FROM duplicate_members dm
        JOIN files f ON dm.file_id = f.file_id
        WHERE dm.group_id = ?
      `).all(group.group_id);

      return {
        ...group,
        members
      };
    });
  }
}
