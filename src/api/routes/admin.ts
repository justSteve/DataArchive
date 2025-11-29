/**
 * Admin API routes
 * Database management, system utilities
 */

import { Router, Request, Response } from 'express';
import { exec } from 'child_process';
import { promisify } from 'util';
import path from 'path';
import fs from 'fs';

const execAsync = promisify(exec);
const router = Router();

/**
 * POST /api/admin/reset-database
 * Reset database to blank slate (with backup)
 */
router.post('/reset-database', async (req: Request, res: Response) => {
  try {
    const { confirm } = req.body;

    if (confirm !== true) {
      return res.status(400).json({
        error: 'Confirmation required',
        message: 'Set confirm=true to reset database'
      });
    }

    console.log('[Admin] Resetting database...');

    const scriptPath = path.join(__dirname, '../../../quick-reset-db.sh');

    // Check if script exists
    if (!fs.existsSync(scriptPath)) {
      return res.status(500).json({
        error: 'Reset script not found',
        path: scriptPath
      });
    }

    // Execute reset script
    const { stdout, stderr } = await execAsync(`bash ${scriptPath}`);

    console.log('[Admin] Database reset complete');
    console.log(stdout);

    if (stderr) {
      console.warn('[Admin] Reset warnings:', stderr);
    }

    res.json({
      success: true,
      message: 'Database reset successfully',
      output: stdout
    });
  } catch (error) {
    console.error('[Admin] Database reset failed:', error);
    res.status(500).json({
      error: 'Failed to reset database',
      message: error instanceof Error ? error.message : String(error)
    });
  }
});

/**
 * GET /api/admin/database-stats
 * Get database statistics
 */
router.get('/database-stats', async (req: Request, res: Response) => {
  try {
    const dbPath = './output/archive.db';

    // Check if database exists
    if (!fs.existsSync(dbPath)) {
      return res.json({
        exists: false,
        size: 0,
        scans: 0,
        drives: 0,
        files: 0
      });
    }

    // Get file size
    const stats = fs.statSync(dbPath);
    const sizeBytes = stats.size;
    const sizeMB = (sizeBytes / (1024 * 1024)).toFixed(2);

    // Get record counts (use DatabaseService)
    const Database = require('better-sqlite3');
    const db = new Database(dbPath);

    const scanCount = db.prepare('SELECT COUNT(*) as count FROM scans').get().count;
    const driveCount = db.prepare('SELECT COUNT(*) as count FROM drives').get().count;
    const fileCount = db.prepare('SELECT SUM(file_count) as count FROM scans WHERE file_count IS NOT NULL').get().count || 0;

    db.close();

    res.json({
      exists: true,
      size_bytes: sizeBytes,
      size_mb: parseFloat(sizeMB),
      scans: scanCount,
      drives: driveCount,
      files: fileCount,
      path: dbPath
    });
  } catch (error) {
    console.error('[Admin] Failed to get database stats:', error);
    res.status(500).json({
      error: 'Failed to get database statistics',
      message: error instanceof Error ? error.message : String(error)
    });
  }
});

/**
 * GET /api/admin/backups
 * List available database backups
 */
router.get('/backups', (req: Request, res: Response) => {
  try {
    const backupDir = './output/backups';

    // Check if backup directory exists
    if (!fs.existsSync(backupDir)) {
      return res.json({ backups: [] });
    }

    // Get all .db files
    const files = fs.readdirSync(backupDir)
      .filter(file => file.endsWith('.db'))
      .map(file => {
        const filePath = path.join(backupDir, file);
        const stats = fs.statSync(filePath);
        return {
          filename: file,
          path: filePath,
          size_bytes: stats.size,
          size_mb: (stats.size / (1024 * 1024)).toFixed(2),
          created: stats.birthtime,
          modified: stats.mtime
        };
      })
      .sort((a, b) => b.modified.getTime() - a.modified.getTime());

    res.json({ backups: files });
  } catch (error) {
    console.error('[Admin] Failed to list backups:', error);
    res.status(500).json({
      error: 'Failed to list backups',
      message: error instanceof Error ? error.message : String(error)
    });
  }
});

export default router;
