/**
 * Recovery Manager
 * Automatic recovery from process failures and task resumption
 */

import { Database } from 'bun:sqlite';
import path from 'path';
import { ProcessMonitor, ProcessInfo } from './ProcessMonitor';
import { CheckpointManager, CheckpointData } from './CheckpointManager';

export interface RecoveryStrategy {
  maxRetries: number;
  retryDelayMs: number;
  backoffMultiplier: number;
  notifyOnFailure: boolean;
}

export interface RecoveryAction {
  actionType: 'restart' | 'resume' | 'skip' | 'manual';
  taskType: string;
  taskId: string;
  reason: string;
  attemptCount: number;
  lastAttempt?: string;
  nextAttempt?: string;
}

export interface RecoveryResult {
  success: boolean;
  action: RecoveryAction;
  message: string;
  error?: string;
}

const DEFAULT_STRATEGIES: Record<string, RecoveryStrategy> = {
  scan: {
    maxRetries: 3,
    retryDelayMs: 60000, // 1 minute
    backoffMultiplier: 2,
    notifyOnFailure: true
  },
  hash_computation: {
    maxRetries: 5,
    retryDelayMs: 30000, // 30 seconds
    backoffMultiplier: 1.5,
    notifyOnFailure: true
  },
  inspection: {
    maxRetries: 2,
    retryDelayMs: 120000, // 2 minutes
    backoffMultiplier: 2,
    notifyOnFailure: true
  },
  default: {
    maxRetries: 3,
    retryDelayMs: 60000,
    backoffMultiplier: 2,
    notifyOnFailure: false
  }
};

export class RecoveryManager {
  private db: Database;
  private processMonitor: ProcessMonitor;
  private checkpointManager: CheckpointManager;
  private strategies: Map<string, RecoveryStrategy>;
  private recoveryAttempts: Map<string, number>; // Track retry counts
  private recoveryTimer?: Timer;

  constructor(
    dbPath: string = './output/archive.db',
    processMonitor?: ProcessMonitor,
    checkpointManager?: CheckpointManager
  ) {
    const fullPath = path.resolve(dbPath);
    this.db = new Database(fullPath);
    this.processMonitor = processMonitor || new ProcessMonitor(dbPath);
    this.checkpointManager = checkpointManager || new CheckpointManager(dbPath);
    this.strategies = new Map(Object.entries(DEFAULT_STRATEGIES));
    this.recoveryAttempts = new Map();
  }

  /**
   * Set custom recovery strategy for a task type
   */
  setStrategy(taskType: string, strategy: Partial<RecoveryStrategy>): void {
    const current = this.strategies.get(taskType) || DEFAULT_STRATEGIES.default;
    this.strategies.set(taskType, { ...current, ...strategy });
    console.log(`[RecoveryManager] Updated strategy for ${taskType}:`, strategy);
  }

  /**
   * Get recovery strategy for a task type
   */
  getStrategy(taskType: string): RecoveryStrategy {
    return this.strategies.get(taskType) || DEFAULT_STRATEGIES.default;
  }

  /**
   * Analyze stalled processes and determine recovery actions
   */
  analyzeFailures(): RecoveryAction[] {
    const stalledProcesses = this.processMonitor.detectStalledProcesses();
    const actions: RecoveryAction[] = [];

    for (const proc of stalledProcesses) {
      const attemptKey = `${proc.processType}:${proc.processId}`;
      const attemptCount = this.recoveryAttempts.get(attemptKey) || 0;
      const strategy = this.getStrategy(proc.processType);

      // Check if we have a checkpoint to resume from
      const hasCheckpoint = this.checkpointManager.hasCheckpoint(
        proc.processType,
        proc.processId,
        'progress'
      );

      let actionType: RecoveryAction['actionType'] = 'restart';
      let reason = `Process stalled (no heartbeat for ${strategy.retryDelayMs / 1000}s)`;

      if (attemptCount >= strategy.maxRetries) {
        actionType = 'manual';
        reason = `Max retries (${strategy.maxRetries}) exceeded`;
      } else if (hasCheckpoint) {
        actionType = 'resume';
        reason = 'Checkpoint available, attempting resume';
      }

      const nextDelay = this.calculateBackoffDelay(
        strategy.retryDelayMs,
        attemptCount,
        strategy.backoffMultiplier
      );

      actions.push({
        actionType,
        taskType: proc.processType,
        taskId: proc.processId,
        reason,
        attemptCount,
        lastAttempt: proc.lastHeartbeatAt,
        nextAttempt: actionType !== 'manual'
          ? new Date(Date.now() + nextDelay).toISOString()
          : undefined
      });
    }

    return actions;
  }

  /**
   * Execute recovery action for a stalled process
   */
  async executeRecovery(action: RecoveryAction): Promise<RecoveryResult> {
    const attemptKey = `${action.taskType}:${action.taskId}`;

    try {
      console.log(`[RecoveryManager] Executing ${action.actionType} for ${attemptKey}`);

      switch (action.actionType) {
        case 'resume':
          return await this.resumeTask(action);

        case 'restart':
          return await this.restartTask(action);

        case 'skip':
          return this.skipTask(action);

        case 'manual':
          return this.requireManualIntervention(action);

        default:
          return {
            success: false,
            action,
            message: `Unknown action type: ${action.actionType}`
          };
      }
    } catch (error: any) {
      console.error(`[RecoveryManager] Recovery failed for ${attemptKey}:`, error);
      return {
        success: false,
        action,
        message: 'Recovery execution failed',
        error: error.message
      };
    }
  }

  /**
   * Resume a task from checkpoint
   */
  private async resumeTask(action: RecoveryAction): Promise<RecoveryResult> {
    const checkpoint = this.checkpointManager.getLatestCheckpoint(
      action.taskType,
      action.taskId
    );

    if (!checkpoint) {
      return {
        success: false,
        action,
        message: 'No checkpoint found for resumption'
      };
    }

    // Record error and create recovery record
    this.recordRecoveryAttempt(action, 'resume', checkpoint.checkpointData);

    // Increment retry counter
    const attemptKey = `${action.taskType}:${action.taskId}`;
    this.recoveryAttempts.set(attemptKey, action.attemptCount + 1);

    return {
      success: true,
      action,
      message: `Task can be resumed from checkpoint: ${checkpoint.checkpointName}`,
    };
  }

  /**
   * Restart a task from beginning
   */
  private async restartTask(action: RecoveryAction): Promise<RecoveryResult> {
    // Record error
    this.recordRecoveryAttempt(action, 'restart', null);

    // Clean up old checkpoints
    this.checkpointManager.deleteTaskCheckpoints(action.taskType, action.taskId);

    // Unregister from process monitor
    this.processMonitor.unregisterProcess(action.taskType, action.taskId);

    // Increment retry counter
    const attemptKey = `${action.taskType}:${action.taskId}`;
    this.recoveryAttempts.set(attemptKey, action.attemptCount + 1);

    return {
      success: true,
      action,
      message: `Task will be restarted from beginning (attempt ${action.attemptCount + 1})`
    };
  }

  /**
   * Skip a task (mark as failed)
   */
  private skipTask(action: RecoveryAction): RecoveryResult {
    this.recordRecoveryAttempt(action, 'skip', null);
    this.processMonitor.unregisterProcess(action.taskType, action.taskId);

    return {
      success: true,
      action,
      message: 'Task skipped and marked as failed'
    };
  }

  /**
   * Require manual intervention
   */
  private requireManualIntervention(action: RecoveryAction): RecoveryResult {
    this.recordRecoveryAttempt(action, 'manual', null);

    return {
      success: false,
      action,
      message: `Manual intervention required after ${action.attemptCount} failed attempts`
    };
  }

  /**
   * Calculate backoff delay with exponential increase
   */
  private calculateBackoffDelay(
    baseDelay: number,
    attemptCount: number,
    multiplier: number
  ): number {
    return baseDelay * Math.pow(multiplier, attemptCount);
  }

  /**
   * Record recovery attempt in database
   */
  private recordRecoveryAttempt(
    action: RecoveryAction,
    recoveryType: string,
    checkpointData: any
  ): void {
    try {
      this.db.prepare(`
        INSERT INTO process_errors
        (error_type, process_id, error_message, error_details, occurred_at, severity)
        VALUES (?, ?, ?, ?, ?, ?)
      `).run(
        action.taskType,
        action.taskId,
        `${recoveryType}: ${action.reason}`,
        JSON.stringify({
          action: action.actionType,
          attemptCount: action.attemptCount,
          checkpoint: checkpointData
        }),
        new Date().toISOString(),
        action.actionType === 'manual' ? 'critical' : 'error'
      );
    } catch (error) {
      console.error('[RecoveryManager] Failed to record recovery attempt:', error);
    }
  }

  /**
   * Get recovery history for a task
   */
  getRecoveryHistory(taskType: string, taskId: string): any[] {
    try {
      const rows = this.db.prepare(`
        SELECT
          error_id,
          error_type,
          process_id,
          error_message,
          error_details,
          occurred_at,
          severity,
          resolved_at,
          resolution_notes
        FROM process_errors
        WHERE error_type = ? AND process_id = ?
        ORDER BY occurred_at DESC
      `).all(taskType, taskId);

      return rows.map((row: any) => ({
        ...row,
        error_details: row.error_details ? JSON.parse(row.error_details) : null
      }));
    } catch (error) {
      console.error('[RecoveryManager] Failed to get recovery history:', error);
      return [];
    }
  }

  /**
   * Start automatic recovery loop
   */
  startAutoRecovery(intervalMs: number = 120000): void {
    if (this.recoveryTimer) {
      console.warn('[RecoveryManager] Auto-recovery already running');
      return;
    }

    console.log(`[RecoveryManager] Starting auto-recovery (interval: ${intervalMs}ms)`);

    this.recoveryTimer = setInterval(async () => {
      const actions = this.analyzeFailures();

      if (actions.length > 0) {
        console.log(`[RecoveryManager] Found ${actions.length} tasks requiring recovery`);

        for (const action of actions) {
          if (action.actionType !== 'manual') {
            const result = await this.executeRecovery(action);
            console.log(`[RecoveryManager] Recovery result:`, result);
          }
        }
      }
    }, intervalMs);
  }

  /**
   * Stop automatic recovery loop
   */
  stopAutoRecovery(): void {
    if (this.recoveryTimer) {
      clearInterval(this.recoveryTimer);
      this.recoveryTimer = undefined;
      console.log('[RecoveryManager] Stopped auto-recovery');
    }
  }

  /**
   * Reset retry counter for a task (for manual retry)
   */
  resetRetryCount(taskType: string, taskId: string): void {
    const attemptKey = `${taskType}:${taskId}`;
    this.recoveryAttempts.delete(attemptKey);
    console.log(`[RecoveryManager] Reset retry count for ${attemptKey}`);
  }

  /**
   * Get recovery statistics
   */
  getStatistics(): {
    totalErrors: number;
    byType: Record<string, number>;
    bySeverity: Record<string, number>;
    unresolvedErrors: number;
  } {
    try {
      const total = this.db.prepare(`
        SELECT COUNT(*) as count FROM process_errors
      `).get() as { count: number };

      const byType = this.db.prepare(`
        SELECT error_type, COUNT(*) as count
        FROM process_errors
        GROUP BY error_type
      `).all() as Array<{ error_type: string; count: number }>;

      const bySeverity = this.db.prepare(`
        SELECT severity, COUNT(*) as count
        FROM process_errors
        GROUP BY severity
      `).all() as Array<{ severity: string; count: number }>;

      const unresolved = this.db.prepare(`
        SELECT COUNT(*) as count
        FROM process_errors
        WHERE resolved_at IS NULL
      `).get() as { count: number };

      return {
        totalErrors: total.count,
        byType: Object.fromEntries(byType.map(r => [r.error_type, r.count])),
        bySeverity: Object.fromEntries(bySeverity.map(r => [r.severity, r.count])),
        unresolvedErrors: unresolved.count
      };
    } catch (error) {
      console.error('[RecoveryManager] Failed to get statistics:', error);
      return {
        totalErrors: 0,
        byType: {},
        bySeverity: {},
        unresolvedErrors: 0
      };
    }
  }

  /**
   * Close and cleanup
   */
  close(): void {
    this.stopAutoRecovery();
    this.db.close();
  }
}
