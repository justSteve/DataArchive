/**
 * Checkpoint Manager
 * Saves and restores state for long-running tasks to enable resumption after crashes
 */

import { Database } from 'bun:sqlite';
import path from 'path';

export interface Checkpoint {
  taskType: string;
  taskId: string;
  checkpointName: string;
  checkpointData: any;
  createdAt: string;
  lastUpdatedAt: string;
}

export interface CheckpointData {
  // Scan checkpoints
  filesProcessed?: number;
  lastPath?: string;
  batchNumber?: number;

  // Hash computation checkpoints
  hashesComputed?: number;
  lastFileId?: number;
  errorCount?: number;

  // Inspection checkpoints
  currentPass?: number;
  passProgress?: number;

  // Generic fields
  [key: string]: any;
}

export class CheckpointManager {
  private db: Database;

  constructor(dbPath: string = './output/archive.db') {
    const fullPath = path.resolve(dbPath);
    this.db = new Database(fullPath);
  }

  /**
   * Save or update a checkpoint
   */
  saveCheckpoint(
    taskType: string,
    taskId: string,
    checkpointName: string,
    data: CheckpointData
  ): boolean {
    try {
      const now = new Date().toISOString();
      const dataJson = JSON.stringify(data);

      // Try to update existing checkpoint first
      const updateResult = this.db.prepare(`
        UPDATE task_checkpoints
        SET checkpoint_data = ?,
            last_updated_at = ?
        WHERE task_type = ? AND task_id = ? AND checkpoint_name = ?
      `).run(dataJson, now, taskType, taskId, checkpointName);

      if (updateResult.changes === 0) {
        // No existing checkpoint, insert new one
        this.db.prepare(`
          INSERT INTO task_checkpoints
          (task_type, task_id, checkpoint_name, checkpoint_data, created_at, last_updated_at)
          VALUES (?, ?, ?, ?, ?, ?)
        `).run(taskType, taskId, checkpointName, dataJson, now, now);
      }

      console.log(`[CheckpointManager] Saved checkpoint: ${taskType}/${taskId}/${checkpointName}`);
      return true;
    } catch (error) {
      console.error(`[CheckpointManager] Failed to save checkpoint (${taskType}/${taskId}/${checkpointName}):`, error);
      return false;
    }
  }

  /**
   * Load a checkpoint
   */
  loadCheckpoint(
    taskType: string,
    taskId: string,
    checkpointName: string
  ): CheckpointData | undefined {
    try {
      const row = this.db.prepare(`
        SELECT checkpoint_data
        FROM task_checkpoints
        WHERE task_type = ? AND task_id = ? AND checkpoint_name = ?
      `).get(taskType, taskId, checkpointName) as { checkpoint_data: string } | undefined;

      if (!row) {
        return undefined;
      }

      const data = JSON.parse(row.checkpoint_data);
      console.log(`[CheckpointManager] Loaded checkpoint: ${taskType}/${taskId}/${checkpointName}`);
      return data;
    } catch (error) {
      console.error(`[CheckpointManager] Failed to load checkpoint (${taskType}/${taskId}/${checkpointName}):`, error);
      return undefined;
    }
  }

  /**
   * Check if a checkpoint exists
   */
  hasCheckpoint(
    taskType: string,
    taskId: string,
    checkpointName: string
  ): boolean {
    try {
      const row = this.db.prepare(`
        SELECT checkpoint_id
        FROM task_checkpoints
        WHERE task_type = ? AND task_id = ? AND checkpoint_name = ?
      `).get(taskType, taskId, checkpointName);

      return row !== undefined;
    } catch (error) {
      console.error(`[CheckpointManager] Failed to check checkpoint existence (${taskType}/${taskId}/${checkpointName}):`, error);
      return false;
    }
  }

  /**
   * Get all checkpoints for a task
   */
  getTaskCheckpoints(taskType: string, taskId: string): Checkpoint[] {
    try {
      const rows = this.db.prepare(`
        SELECT
          task_type as taskType,
          task_id as taskId,
          checkpoint_name as checkpointName,
          checkpoint_data as checkpointData,
          created_at as createdAt,
          last_updated_at as lastUpdatedAt
        FROM task_checkpoints
        WHERE task_type = ? AND task_id = ?
        ORDER BY last_updated_at DESC
      `).all(taskType, taskId) as any[];

      return rows.map(row => ({
        ...row,
        checkpointData: JSON.parse(row.checkpointData)
      }));
    } catch (error) {
      console.error(`[CheckpointManager] Failed to get task checkpoints (${taskType}/${taskId}):`, error);
      return [];
    }
  }

  /**
   * Delete a specific checkpoint
   */
  deleteCheckpoint(
    taskType: string,
    taskId: string,
    checkpointName: string
  ): boolean {
    try {
      const result = this.db.prepare(`
        DELETE FROM task_checkpoints
        WHERE task_type = ? AND task_id = ? AND checkpoint_name = ?
      `).run(taskType, taskId, checkpointName);

      if (result.changes > 0) {
        console.log(`[CheckpointManager] Deleted checkpoint: ${taskType}/${taskId}/${checkpointName}`);
      }

      return result.changes > 0;
    } catch (error) {
      console.error(`[CheckpointManager] Failed to delete checkpoint (${taskType}/${taskId}/${checkpointName}):`, error);
      return false;
    }
  }

  /**
   * Delete all checkpoints for a task
   */
  deleteTaskCheckpoints(taskType: string, taskId: string): number {
    try {
      const result = this.db.prepare(`
        DELETE FROM task_checkpoints
        WHERE task_type = ? AND task_id = ?
      `).run(taskType, taskId);

      if (result.changes > 0) {
        console.log(`[CheckpointManager] Deleted ${result.changes} checkpoints for ${taskType}/${taskId}`);
      }

      return result.changes;
    } catch (error) {
      console.error(`[CheckpointManager] Failed to delete task checkpoints (${taskType}/${taskId}):`, error);
      return 0;
    }
  }

  /**
   * Get latest checkpoint for a task (most recently updated)
   */
  getLatestCheckpoint(taskType: string, taskId: string): Checkpoint | undefined {
    try {
      const row = this.db.prepare(`
        SELECT
          task_type as taskType,
          task_id as taskId,
          checkpoint_name as checkpointName,
          checkpoint_data as checkpointData,
          created_at as createdAt,
          last_updated_at as lastUpdatedAt
        FROM task_checkpoints
        WHERE task_type = ? AND task_id = ?
        ORDER BY last_updated_at DESC
        LIMIT 1
      `).get(taskType, taskId) as any;

      if (!row) return undefined;

      return {
        ...row,
        checkpointData: JSON.parse(row.checkpointData)
      };
    } catch (error) {
      console.error(`[CheckpointManager] Failed to get latest checkpoint (${taskType}/${taskId}):`, error);
      return undefined;
    }
  }

  /**
   * Find tasks that have checkpoints (for resumption)
   */
  getResumableTasks(taskType?: string): Array<{ taskType: string; taskId: string; checkpointCount: number }> {
    try {
      let query = `
        SELECT
          task_type,
          task_id,
          COUNT(*) as checkpoint_count
        FROM task_checkpoints
      `;

      let params: any[] = [];

      if (taskType) {
        query += ` WHERE task_type = ?`;
        params.push(taskType);
      }

      query += `
        GROUP BY task_type, task_id
        ORDER BY MAX(last_updated_at) DESC
      `;

      const rows = this.db.prepare(query).all(...params) as Array<{
        task_type: string;
        task_id: string;
        checkpoint_count: number;
      }>;

      return rows.map(row => ({
        taskType: row.task_type,
        taskId: row.task_id,
        checkpointCount: row.checkpoint_count
      }));
    } catch (error) {
      console.error('[CheckpointManager] Failed to get resumable tasks:', error);
      return [];
    }
  }

  /**
   * Clean up old checkpoints (older than specified days)
   */
  cleanup(olderThanDays: number = 7): number {
    try {
      const cutoffTime = new Date(Date.now() - olderThanDays * 24 * 60 * 60 * 1000).toISOString();

      const result = this.db.prepare(`
        DELETE FROM task_checkpoints
        WHERE last_updated_at < ?
      `).run(cutoffTime);

      if (result.changes > 0) {
        console.log(`[CheckpointManager] Cleaned up ${result.changes} old checkpoints`);
      }

      return result.changes;
    } catch (error) {
      console.error('[CheckpointManager] Failed to cleanup old checkpoints:', error);
      return 0;
    }
  }

  /**
   * Get checkpoint statistics
   */
  getStatistics(): {
    totalCheckpoints: number;
    byTaskType: Record<string, number>;
    oldestCheckpoint?: string;
    newestCheckpoint?: string;
  } {
    try {
      // Total count
      const total = this.db.prepare(`
        SELECT COUNT(*) as count FROM task_checkpoints
      `).get() as { count: number };

      // By task type
      const byType = this.db.prepare(`
        SELECT task_type, COUNT(*) as count
        FROM task_checkpoints
        GROUP BY task_type
      `).all() as Array<{ task_type: string; count: number }>;

      const byTaskType: Record<string, number> = {};
      for (const row of byType) {
        byTaskType[row.task_type] = row.count;
      }

      // Oldest and newest
      const oldest = this.db.prepare(`
        SELECT created_at FROM task_checkpoints ORDER BY created_at ASC LIMIT 1
      `).get() as { created_at: string } | undefined;

      const newest = this.db.prepare(`
        SELECT last_updated_at FROM task_checkpoints ORDER BY last_updated_at DESC LIMIT 1
      `).get() as { last_updated_at: string } | undefined;

      return {
        totalCheckpoints: total.count,
        byTaskType,
        oldestCheckpoint: oldest?.created_at,
        newestCheckpoint: newest?.last_updated_at
      };
    } catch (error) {
      console.error('[CheckpointManager] Failed to get statistics:', error);
      return {
        totalCheckpoints: 0,
        byTaskType: {}
      };
    }
  }

  /**
   * Close database connection
   */
  close(): void {
    this.db.close();
  }
}
