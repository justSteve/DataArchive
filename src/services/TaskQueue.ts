/**
 * Task Queue
 * Prioritized task queue with scheduling and execution management
 */

export interface Task {
  id: string;
  type: string;
  priority: number; // Higher = more important
  payload: any;
  createdAt: string;
  scheduledFor?: string; // When to execute (ISO timestamp)
  maxRetries: number;
  retryCount: number;
  lastError?: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
}

export interface TaskResult {
  taskId: string;
  success: boolean;
  result?: any;
  error?: string;
  duration: number;
}

export type TaskExecutor = (task: Task) => Promise<TaskResult>;

export interface QueueStats {
  pending: number;
  running: number;
  completed: number;
  failed: number;
  cancelled: number;
  totalProcessed: number;
}

export class TaskQueue {
  private tasks: Map<string, Task>;
  private executors: Map<string, TaskExecutor>;
  private running: Set<string>;
  private maxConcurrent: number;
  private pollInterval: number;
  private pollTimer?: Timer;
  private isProcessing: boolean;

  constructor(maxConcurrent: number = 3, pollIntervalMs: number = 1000) {
    this.tasks = new Map();
    this.executors = new Map();
    this.running = new Set();
    this.maxConcurrent = maxConcurrent;
    this.pollInterval = pollIntervalMs;
    this.isProcessing = false;
  }

  /**
   * Register a task executor for a specific task type
   */
  registerExecutor(taskType: string, executor: TaskExecutor): void {
    this.executors.set(taskType, executor);
    console.log(`[TaskQueue] Registered executor for task type: ${taskType}`);
  }

  /**
   * Add a task to the queue
   */
  enqueue(task: Omit<Task, 'id' | 'createdAt' | 'status' | 'retryCount'>): string {
    const id = `task_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
    const fullTask: Task = {
      ...task,
      id,
      createdAt: new Date().toISOString(),
      status: 'pending',
      retryCount: 0
    };

    this.tasks.set(id, fullTask);
    console.log(`[TaskQueue] Enqueued task ${id} (type: ${task.type}, priority: ${task.priority})`);

    // Start processing if not already running
    if (!this.isProcessing) {
      this.startProcessing();
    }

    return id;
  }

  /**
   * Get a task by ID
   */
  getTask(taskId: string): Task | undefined {
    return this.tasks.get(taskId);
  }

  /**
   * Cancel a pending task
   */
  cancelTask(taskId: string): boolean {
    const task = this.tasks.get(taskId);

    if (!task) {
      return false;
    }

    if (task.status === 'running') {
      console.warn(`[TaskQueue] Cannot cancel running task ${taskId}`);
      return false;
    }

    if (task.status === 'pending') {
      task.status = 'cancelled';
      console.log(`[TaskQueue] Cancelled task ${taskId}`);
      return true;
    }

    return false;
  }

  /**
   * Retry a failed task
   */
  retryTask(taskId: string): boolean {
    const task = this.tasks.get(taskId);

    if (!task || task.status !== 'failed') {
      return false;
    }

    if (task.retryCount >= task.maxRetries) {
      console.warn(`[TaskQueue] Task ${taskId} has reached max retries (${task.maxRetries})`);
      return false;
    }

    task.status = 'pending';
    task.retryCount++;
    task.lastError = undefined;

    console.log(`[TaskQueue] Retry ${task.retryCount}/${task.maxRetries} for task ${taskId}`);

    // Resume processing if stopped
    if (!this.isProcessing) {
      this.startProcessing();
    }

    return true;
  }

  /**
   * Get tasks by status
   */
  getTasksByStatus(status: Task['status']): Task[] {
    return Array.from(this.tasks.values()).filter(t => t.status === status);
  }

  /**
   * Get queue statistics
   */
  getStats(): QueueStats {
    const tasks = Array.from(this.tasks.values());

    return {
      pending: tasks.filter(t => t.status === 'pending').length,
      running: tasks.filter(t => t.status === 'running').length,
      completed: tasks.filter(t => t.status === 'completed').length,
      failed: tasks.filter(t => t.status === 'failed').length,
      cancelled: tasks.filter(t => t.status === 'cancelled').length,
      totalProcessed: tasks.length
    };
  }

  /**
   * Get next task to execute (highest priority, earliest scheduled)
   */
  private getNextTask(): Task | undefined {
    const now = new Date().toISOString();
    const pending = this.getTasksByStatus('pending');

    // Filter tasks that are ready to execute
    const ready = pending.filter(t => !t.scheduledFor || t.scheduledFor <= now);

    if (ready.length === 0) {
      return undefined;
    }

    // Sort by priority (desc) then createdAt (asc)
    ready.sort((a, b) => {
      if (b.priority !== a.priority) {
        return b.priority - a.priority;
      }
      return a.createdAt.localeCompare(b.createdAt);
    });

    return ready[0];
  }

  /**
   * Execute a single task
   */
  private async executeTask(task: Task): Promise<void> {
    const executor = this.executors.get(task.type);

    if (!executor) {
      console.error(`[TaskQueue] No executor registered for task type: ${task.type}`);
      task.status = 'failed';
      task.lastError = `No executor registered for type: ${task.type}`;
      return;
    }

    task.status = 'running';
    this.running.add(task.id);
    const startTime = Date.now();

    console.log(`[TaskQueue] Executing task ${task.id} (type: ${task.type})`);

    try {
      const result = await executor(task);
      const duration = Date.now() - startTime;

      if (result.success) {
        task.status = 'completed';
        console.log(`[TaskQueue] Task ${task.id} completed in ${duration}ms`);
      } else {
        task.status = 'failed';
        task.lastError = result.error;
        console.error(`[TaskQueue] Task ${task.id} failed: ${result.error}`);

        // Auto-retry if retries remain
        if (task.retryCount < task.maxRetries) {
          console.log(`[TaskQueue] Auto-retrying task ${task.id} (${task.retryCount + 1}/${task.maxRetries})`);
          this.retryTask(task.id);
        }
      }
    } catch (error: any) {
      task.status = 'failed';
      task.lastError = error.message || 'Unknown error';
      console.error(`[TaskQueue] Task ${task.id} threw exception:`, error);

      // Auto-retry if retries remain
      if (task.retryCount < task.maxRetries) {
        this.retryTask(task.id);
      }
    } finally {
      this.running.delete(task.id);
    }
  }

  /**
   * Process queue - execute tasks up to concurrency limit
   */
  private async processQueue(): Promise<void> {
    if (this.running.size >= this.maxConcurrent) {
      // At max concurrency, wait for next poll
      return;
    }

    const availableSlots = this.maxConcurrent - this.running.size;
    const tasksToStart: Task[] = [];

    // Get next tasks to execute
    for (let i = 0; i < availableSlots; i++) {
      const task = this.getNextTask();
      if (task) {
        tasksToStart.push(task);
      } else {
        break; // No more ready tasks
      }
    }

    // Execute tasks in parallel
    if (tasksToStart.length > 0) {
      await Promise.all(tasksToStart.map(t => this.executeTask(t)));
    }
  }

  /**
   * Start queue processing loop
   */
  startProcessing(): void {
    if (this.isProcessing) {
      return;
    }

    this.isProcessing = true;
    console.log(`[TaskQueue] Starting queue processing (concurrency: ${this.maxConcurrent}, poll: ${this.pollInterval}ms)`);

    this.pollTimer = setInterval(async () => {
      await this.processQueue();

      // Stop processing if queue is empty and nothing running
      const stats = this.getStats();
      if (stats.pending === 0 && stats.running === 0) {
        this.stopProcessing();
      }
    }, this.pollInterval);
  }

  /**
   * Stop queue processing loop
   */
  stopProcessing(): void {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = undefined;
      this.isProcessing = false;
      console.log('[TaskQueue] Stopped queue processing');
    }
  }

  /**
   * Wait for all running tasks to complete
   */
  async drain(): Promise<void> {
    console.log('[TaskQueue] Draining queue...');

    return new Promise((resolve) => {
      const checkInterval = setInterval(() => {
        const stats = this.getStats();
        if (stats.running === 0 && stats.pending === 0) {
          clearInterval(checkInterval);
          console.log('[TaskQueue] Queue drained');
          resolve();
        }
      }, 100);
    });
  }

  /**
   * Clear all tasks (pending, completed, failed)
   */
  clear(includeRunning: boolean = false): void {
    if (includeRunning) {
      console.warn('[TaskQueue] Clearing all tasks including running tasks');
      this.tasks.clear();
      this.running.clear();
    } else {
      const running = Array.from(this.running);
      this.tasks.clear();

      // Restore running tasks
      for (const taskId of running) {
        const task = this.tasks.get(taskId);
        if (task) {
          this.tasks.set(taskId, task);
        }
      }

      console.log(`[TaskQueue] Cleared queue (preserved ${running.length} running tasks)`);
    }
  }

  /**
   * Cleanup and shutdown
   */
  async shutdown(): Promise<void> {
    console.log('[TaskQueue] Shutting down...');
    this.stopProcessing();
    await this.drain();
    this.clear(true);
    console.log('[TaskQueue] Shutdown complete');
  }
}
