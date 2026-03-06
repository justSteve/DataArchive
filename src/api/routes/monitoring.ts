/**
 * Monitoring API Routes
 * Expose ProcessMonitor and CheckpointManager functionality
 */

import { Router } from 'express';
import { ProcessMonitor } from '../../services/ProcessMonitor';
import { CheckpointManager } from '../../services/CheckpointManager';

const router = Router();

// Initialize services
const processMonitor = new ProcessMonitor();
const checkpointManager = new CheckpointManager();

// Start auto-detection on server startup
processMonitor.startAutoDetection(60000); // Check every minute

// ==============================================
// PROCESS MONITORING ENDPOINTS
// ==============================================

/**
 * GET /api/monitoring/processes
 * Get all active processes
 */
router.get('/processes', (req, res) => {
  try {
    const processes = processMonitor.getActiveProcesses();
    res.json({
      success: true,
      data: processes,
      count: processes.length
    });
  } catch (error: any) {
    console.error('[API] Failed to get active processes:', error);
    res.status(500).json({
      success: false,
      error: error.message || 'Failed to get active processes'
    });
  }
});

/**
 * GET /api/monitoring/processes/:processType
 * Get processes by type
 */
router.get('/processes/:processType', (req, res) => {
  try {
    const { processType } = req.params;
    const processes = processMonitor.getProcessesByType(processType);
    res.json({
      success: true,
      data: processes,
      count: processes.length
    });
  } catch (error: any) {
    console.error(`[API] Failed to get processes by type:`, error);
    res.status(500).json({
      success: false,
      error: error.message || 'Failed to get processes'
    });
  }
});

/**
 * GET /api/monitoring/processes/:processType/:processId
 * Get a specific process
 */
router.get('/processes/:processType/:processId', (req, res) => {
  try {
    const { processType, processId } = req.params;
    const process = processMonitor.getProcess(processType, processId);

    if (!process) {
      return res.status(404).json({
        success: false,
        error: 'Process not found'
      });
    }

    res.json({
      success: true,
      data: process
    });
  } catch (error: any) {
    console.error(`[API] Failed to get process:`, error);
    res.status(500).json({
      success: false,
      error: error.message || 'Failed to get process'
    });
  }
});

/**
 * POST /api/monitoring/processes/register
 * Register a new process
 */
router.post('/processes/register', (req, res) => {
  try {
    const { processType, processId, hostInfo } = req.body;

    if (!processType || !processId) {
      return res.status(400).json({
        success: false,
        error: 'processType and processId are required'
      });
    }

    const success = processMonitor.registerProcess(processType, processId, hostInfo);

    res.json({
      success,
      message: success ? 'Process registered' : 'Failed to register process'
    });
  } catch (error: any) {
    console.error('[API] Failed to register process:', error);
    res.status(500).json({
      success: false,
      error: error.message || 'Failed to register process'
    });
  }
});

/**
 * POST /api/monitoring/processes/heartbeat
 * Update process heartbeat
 */
router.post('/processes/heartbeat', (req, res) => {
  try {
    const { processType, processId, status, progressPct, progressDetails } = req.body;

    if (!processType || !processId || !status) {
      return res.status(400).json({
        success: false,
        error: 'processType, processId, and status are required'
      });
    }

    const success = processMonitor.updateHeartbeat({
      processType,
      processId,
      status,
      progressPct,
      progressDetails
    });

    res.json({
      success,
      message: success ? 'Heartbeat updated' : 'Failed to update heartbeat'
    });
  } catch (error: any) {
    console.error('[API] Failed to update heartbeat:', error);
    res.status(500).json({
      success: false,
      error: error.message || 'Failed to update heartbeat'
    });
  }
});

/**
 * DELETE /api/monitoring/processes/:processType/:processId
 * Unregister a process
 */
router.delete('/processes/:processType/:processId', (req, res) => {
  try {
    const { processType, processId } = req.params;
    const success = processMonitor.unregisterProcess(processType, processId);

    res.json({
      success,
      message: success ? 'Process unregistered' : 'Failed to unregister process'
    });
  } catch (error: any) {
    console.error('[API] Failed to unregister process:', error);
    res.status(500).json({
      success: false,
      error: error.message || 'Failed to unregister process'
    });
  }
});

/**
 * GET /api/monitoring/stalled
 * Get stalled processes
 */
router.get('/stalled', (req, res) => {
  try {
    const stalled = processMonitor.detectStalledProcesses();
    res.json({
      success: true,
      data: stalled,
      count: stalled.length
    });
  } catch (error: any) {
    console.error('[API] Failed to detect stalled processes:', error);
    res.status(500).json({
      success: false,
      error: error.message || 'Failed to detect stalled processes'
    });
  }
});

/**
 * GET /api/monitoring/statistics
 * Get monitoring statistics
 */
router.get('/statistics', (req, res) => {
  try {
    const stats = processMonitor.getStatistics();
    res.json({
      success: true,
      data: stats
    });
  } catch (error: any) {
    console.error('[API] Failed to get statistics:', error);
    res.status(500).json({
      success: false,
      error: error.message || 'Failed to get statistics'
    });
  }
});

// ==============================================
// CHECKPOINT ENDPOINTS
// ==============================================

/**
 * POST /api/monitoring/checkpoints
 * Save a checkpoint
 */
router.post('/checkpoints', (req, res) => {
  try {
    const { taskType, taskId, checkpointName, data } = req.body;

    if (!taskType || !taskId || !checkpointName || !data) {
      return res.status(400).json({
        success: false,
        error: 'taskType, taskId, checkpointName, and data are required'
      });
    }

    const success = checkpointManager.saveCheckpoint(taskType, taskId, checkpointName, data);

    res.json({
      success,
      message: success ? 'Checkpoint saved' : 'Failed to save checkpoint'
    });
  } catch (error: any) {
    console.error('[API] Failed to save checkpoint:', error);
    res.status(500).json({
      success: false,
      error: error.message || 'Failed to save checkpoint'
    });
  }
});

/**
 * GET /api/monitoring/checkpoints/:taskType/:taskId/:checkpointName
 * Load a specific checkpoint
 */
router.get('/checkpoints/:taskType/:taskId/:checkpointName', (req, res) => {
  try {
    const { taskType, taskId, checkpointName } = req.params;
    const data = checkpointManager.loadCheckpoint(taskType, taskId, checkpointName);

    if (!data) {
      return res.status(404).json({
        success: false,
        error: 'Checkpoint not found'
      });
    }

    res.json({
      success: true,
      data
    });
  } catch (error: any) {
    console.error('[API] Failed to load checkpoint:', error);
    res.status(500).json({
      success: false,
      error: error.message || 'Failed to load checkpoint'
    });
  }
});

/**
 * GET /api/monitoring/checkpoints/:taskType/:taskId
 * Get all checkpoints for a task
 */
router.get('/checkpoints/:taskType/:taskId', (req, res) => {
  try {
    const { taskType, taskId } = req.params;
    const checkpoints = checkpointManager.getTaskCheckpoints(taskType, taskId);

    res.json({
      success: true,
      data: checkpoints,
      count: checkpoints.length
    });
  } catch (error: any) {
    console.error('[API] Failed to get task checkpoints:', error);
    res.status(500).json({
      success: false,
      error: error.message || 'Failed to get checkpoints'
    });
  }
});

/**
 * GET /api/monitoring/resumable
 * Get tasks that can be resumed
 */
router.get('/resumable', (req, res) => {
  try {
    const taskType = req.query.taskType as string | undefined;
    const tasks = checkpointManager.getResumableTasks(taskType);

    res.json({
      success: true,
      data: tasks,
      count: tasks.length
    });
  } catch (error: any) {
    console.error('[API] Failed to get resumable tasks:', error);
    res.status(500).json({
      success: false,
      error: error.message || 'Failed to get resumable tasks'
    });
  }
});

/**
 * DELETE /api/monitoring/checkpoints/:taskType/:taskId
 * Delete all checkpoints for a task
 */
router.delete('/checkpoints/:taskType/:taskId', (req, res) => {
  try {
    const { taskType, taskId } = req.params;
    const deletedCount = checkpointManager.deleteTaskCheckpoints(taskType, taskId);

    res.json({
      success: true,
      deletedCount,
      message: `Deleted ${deletedCount} checkpoint(s)`
    });
  } catch (error: any) {
    console.error('[API] Failed to delete checkpoints:', error);
    res.status(500).json({
      success: false,
      error: error.message || 'Failed to delete checkpoints'
    });
  }
});

/**
 * GET /api/monitoring/checkpoints/statistics
 * Get checkpoint statistics
 */
router.get('/checkpoints/statistics', (req, res) => {
  try {
    const stats = checkpointManager.getStatistics();

    res.json({
      success: true,
      data: stats
    });
  } catch (error: any) {
    console.error('[API] Failed to get checkpoint statistics:', error);
    res.status(500).json({
      success: false,
      error: error.message || 'Failed to get statistics'
    });
  }
});

// Cleanup on server shutdown
process.on('SIGTERM', () => {
  console.log('[Monitoring] Cleaning up...');
  processMonitor.stopAutoDetection();
  processMonitor.close();
  checkpointManager.close();
});

export default router;
