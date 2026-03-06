/**
 * Process Monitoring Service
 * Tracks active processes, monitors health, detects stalls
 */

import { Database } from 'bun:sqlite';
import path from 'path';

export interface ProcessInfo {
  processType: string;      // 'scan', 'inspection', 'hash_worker', etc.
  processId: string;         // scan_id, session_id, PID, etc.
  startedAt: string;
  lastHeartbeatAt: string;
  status: 'running' | 'idle' | 'waiting' | 'stalled';
  progressPct: number;
  progressDetails?: any;
  hostInfo?: string;
}

export interface HeartbeatUpdate {
  processType: string;
  processId: string;
  status: 'running' | 'idle' | 'waiting' | 'stalled';
  progressPct?: number;
  progressDetails?: any;
}

export class ProcessMonitor {
  private db: Database;
  private staleThresholdMs: number;
  private checkInterval?: Timer;

  constructor(dbPath: string = './output/archive.db', staleThresholdMs: number = 300000) {
    const fullPath = path.resolve(dbPath);
    this.db = new Database(fullPath);
    this.staleThresholdMs = staleThresholdMs; // Default: 5 minutes
  }

  /**
   * Register a new process for monitoring
   */
  registerProcess(
    processType: string,
    processId: string,
    hostInfo?: string
  ): boolean {
    try {
      const now = new Date().toISOString();

      // Check if process already exists
      const existing = this.db.prepare(`
        SELECT heartbeat_id FROM process_heartbeats
        WHERE process_type = ? AND process_id = ?
      `).get(processType, processId);

      if (existing) {
        // Update existing process
        this.db.prepare(`
          UPDATE process_heartbeats
          SET started_at = ?, last_heartbeat_at = ?, status = 'running', progress_pct = 0.0
          WHERE process_type = ? AND process_id = ?
        `).run(now, now, processType, processId);
      } else {
        // Insert new process
        this.db.prepare(`
          INSERT INTO process_heartbeats
          (process_type, process_id, started_at, last_heartbeat_at, status, progress_pct, host_info)
          VALUES (?, ?, ?, ?, 'running', 0.0, ?)
        `).run(processType, processId, now, now, now, hostInfo || null);
      }

      console.log(`[ProcessMonitor] Registered process: ${processType}/${processId}`);
      return true;
    } catch (error) {
      console.error(`[ProcessMonitor] Failed to register process (${processType}/${processId}):`, error);
      return false;
    }
  }

  /**
   * Update heartbeat for an active process
   */
  updateHeartbeat(update: HeartbeatUpdate): boolean {
    try {
      const now = new Date().toISOString();
      const progressDetails = update.progressDetails
        ? JSON.stringify(update.progressDetails)
        : null;

      this.db.prepare(`
        UPDATE process_heartbeats
        SET last_heartbeat_at = ?,
            status = ?,
            progress_pct = ?,
            progress_details = ?
        WHERE process_type = ? AND process_id = ?
      `).run(
        now,
        update.status,
        update.progressPct ?? 0.0,
        progressDetails,
        update.processType,
        update.processId
      );

      return true;
    } catch (error) {
      console.error(`[ProcessMonitor] Failed to update heartbeat (${update.processType}/${update.processId}):`, error);
      return false;
    }
  }

  /**
   * Unregister a process (completed or cancelled)
   */
  unregisterProcess(processType: string, processId: string): boolean {
    try {
      this.db.prepare(`
        DELETE FROM process_heartbeats
        WHERE process_type = ? AND process_id = ?
      `).run(processType, processId);

      console.log(`[ProcessMonitor] Unregistered process: ${processType}/${processId}`);
      return true;
    } catch (error) {
      console.error(`[ProcessMonitor] Failed to unregister process (${processType}/${processId}):`, error);
      return false;
    }
  }

  /**
   * Get all active processes
   */
  getActiveProcesses(): ProcessInfo[] {
    try {
      const rows = this.db.prepare(`
        SELECT
          process_type as processType,
          process_id as processId,
          started_at as startedAt,
          last_heartbeat_at as lastHeartbeatAt,
          status,
          progress_pct as progressPct,
          progress_details as progressDetails,
          host_info as hostInfo
        FROM process_heartbeats
        ORDER BY started_at DESC
      `).all() as any[];

      return rows.map(row => ({
        ...row,
        progressDetails: row.progressDetails ? JSON.parse(row.progressDetails) : undefined
      }));
    } catch (error) {
      console.error('[ProcessMonitor] Failed to get active processes:', error);
      return [];
    }
  }

  /**
   * Get processes by type
   */
  getProcessesByType(processType: string): ProcessInfo[] {
    try {
      const rows = this.db.prepare(`
        SELECT
          process_type as processType,
          process_id as processId,
          started_at as startedAt,
          last_heartbeat_at as lastHeartbeatAt,
          status,
          progress_pct as progressPct,
          progress_details as progressDetails,
          host_info as hostInfo
        FROM process_heartbeats
        WHERE process_type = ?
        ORDER BY started_at DESC
      `).all(processType) as any[];

      return rows.map(row => ({
        ...row,
        progressDetails: row.progressDetails ? JSON.parse(row.progressDetails) : undefined
      }));
    } catch (error) {
      console.error(`[ProcessMonitor] Failed to get processes by type (${processType}):`, error);
      return [];
    }
  }

  /**
   * Get a specific process
   */
  getProcess(processType: string, processId: string): ProcessInfo | undefined {
    try {
      const row = this.db.prepare(`
        SELECT
          process_type as processType,
          process_id as processId,
          started_at as startedAt,
          last_heartbeat_at as lastHeartbeatAt,
          status,
          progress_pct as progressPct,
          progress_details as progressDetails,
          host_info as hostInfo
        FROM process_heartbeats
        WHERE process_type = ? AND process_id = ?
      `).get(processType, processId) as any;

      if (!row) return undefined;

      return {
        ...row,
        progressDetails: row.progressDetails ? JSON.parse(row.progressDetails) : undefined
      };
    } catch (error) {
      console.error(`[ProcessMonitor] Failed to get process (${processType}/${processId}):`, error);
      return undefined;
    }
  }

  /**
   * Detect stalled processes (no heartbeat within threshold)
   */
  detectStalledProcesses(): ProcessInfo[] {
    try {
      const thresholdTime = new Date(Date.now() - this.staleThresholdMs).toISOString();

      const rows = this.db.prepare(`
        SELECT
          process_type as processType,
          process_id as processId,
          started_at as startedAt,
          last_heartbeat_at as lastHeartbeatAt,
          status,
          progress_pct as progressPct,
          progress_details as progressDetails,
          host_info as hostInfo
        FROM process_heartbeats
        WHERE last_heartbeat_at < ?
          AND status != 'stalled'
        ORDER BY last_heartbeat_at ASC
      `).all(thresholdTime) as any[];

      // Mark as stalled
      for (const row of rows) {
        this.db.prepare(`
          UPDATE process_heartbeats
          SET status = 'stalled'
          WHERE process_type = ? AND process_id = ?
        `).run(row.processType, row.processId);
      }

      if (rows.length > 0) {
        console.warn(`[ProcessMonitor] Detected ${rows.length} stalled processes`);
      }

      return rows.map(row => ({
        ...row,
        status: 'stalled' as const,
        progressDetails: row.progressDetails ? JSON.parse(row.progressDetails) : undefined
      }));
    } catch (error) {
      console.error('[ProcessMonitor] Failed to detect stalled processes:', error);
      return [];
    }
  }

  /**
   * Start automatic stall detection (checks every interval)
   */
  startAutoDetection(intervalMs: number = 60000): void {
    if (this.checkInterval) {
      console.warn('[ProcessMonitor] Auto-detection already running');
      return;
    }

    console.log(`[ProcessMonitor] Starting auto-detection (interval: ${intervalMs}ms, threshold: ${this.staleThresholdMs}ms)`);

    this.checkInterval = setInterval(() => {
      const stalled = this.detectStalledProcesses();
      if (stalled.length > 0) {
        console.warn(`[ProcessMonitor] Auto-detection found ${stalled.length} stalled processes:`,
          stalled.map(p => `${p.processType}/${p.processId}`));
      }
    }, intervalMs);
  }

  /**
   * Stop automatic stall detection
   */
  stopAutoDetection(): void {
    if (this.checkInterval) {
      clearInterval(this.checkInterval);
      this.checkInterval = undefined;
      console.log('[ProcessMonitor] Stopped auto-detection');
    }
  }

  /**
   * Get monitoring statistics
   */
  getStatistics(): {
    totalProcesses: number;
    byType: Record<string, number>;
    byStatus: Record<string, number>;
    stalledProcesses: number;
  } {
    try {
      const all = this.getActiveProcesses();

      const byType: Record<string, number> = {};
      const byStatus: Record<string, number> = {};
      let stalledCount = 0;

      for (const proc of all) {
        byType[proc.processType] = (byType[proc.processType] || 0) + 1;
        byStatus[proc.status] = (byStatus[proc.status] || 0) + 1;
        if (proc.status === 'stalled') stalledCount++;
      }

      return {
        totalProcesses: all.length,
        byType,
        byStatus,
        stalledProcesses: stalledCount
      };
    } catch (error) {
      console.error('[ProcessMonitor] Failed to get statistics:', error);
      return {
        totalProcesses: 0,
        byType: {},
        byStatus: {},
        stalledProcesses: 0
      };
    }
  }

  /**
   * Clean up old completed process records
   */
  cleanup(): void {
    try {
      // Remove records older than 24 hours
      const cutoffTime = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();

      const result = this.db.prepare(`
        DELETE FROM process_heartbeats
        WHERE last_heartbeat_at < ?
      `).run(cutoffTime);

      if (result.changes > 0) {
        console.log(`[ProcessMonitor] Cleaned up ${result.changes} old process records`);
      }
    } catch (error) {
      console.error('[ProcessMonitor] Failed to cleanup old records:', error);
    }
  }

  /**
   * Close database connection
   */
  close(): void {
    this.stopAutoDetection();
    this.db.close();
  }
}
