/**
 * Scan management API routes
 */

import { Router, Request, Response } from 'express';
import { DatabaseService } from '../../services/DatabaseService';
import { PythonBridge } from '../../services/PythonBridge';

const router = Router();
const db = new DatabaseService();
const bridge = new PythonBridge();

/**
 * GET /api/scans
 * List all scans
 */
router.get('/', async (req: Request, res: Response) => {
  try {
    const scans = db.getScans();
    res.json(scans);
  } catch (error) {
    console.error('Error fetching scans:', error);
    res.status(500).json({ error: 'Failed to fetch scans' });
  }
});

/**
 * GET /api/scans/:id
 * Get a specific scan
 */
router.get('/:id', async (req: Request, res: Response) => {
  try {
    const scanId = parseInt(req.params.id);
    const scan = db.getScan(scanId);

    if (!scan) {
      return res.status(404).json({ error: 'Scan not found' });
    }

    // Include OS info if available
    const osInfo = db.getOSInfo(scanId);
    const fileCount = db.getFileCount(scanId);

    res.json({
      ...scan,
      os_info: osInfo,
      file_count: fileCount
    });
  } catch (error) {
    console.error('Error fetching scan:', error);
    res.status(500).json({ error: 'Failed to fetch scan' });
  }
});

/**
 * POST /api/scans/start
 * Start a new scan
 */
router.post('/start', async (req: Request, res: Response) => {
  try {
    const { drivePath, dbPath, options } = req.body;

    if (!drivePath) {
      return res.status(400).json({ error: 'drivePath is required' });
    }

    const defaultDbPath = dbPath || './output/archive.db';

    // Validate drive first
    console.log(`[API] Validating drive: ${drivePath}`);
    const validation = await bridge.validateDrive(drivePath);

    if (!validation.valid) {
      return res.status(400).json({
        error: 'Drive validation failed',
        validation
      });
    }

    // Start scan using Python bridge
    console.log(`[API] Starting scan: ${drivePath}`);
    const result = await bridge.scanDrive(drivePath, defaultDbPath, options || {});

    res.json({
      success: true,
      scan_id: result.scan_id,
      file_count: result.file_count,
      total_size: result.total_size,
      status: result.status
    });
  } catch (error) {
    console.error('Error starting scan:', error);
    res.status(500).json({
      error: 'Failed to start scan',
      message: error instanceof Error ? error.message : String(error)
    });
  }
});

/**
 * GET /api/scans/:id/status
 * Get scan status (for real-time updates)
 */
router.get('/:id/status', async (req: Request, res: Response) => {
  try {
    const scanId = parseInt(req.params.id);
    const scan = db.getScan(scanId);

    if (!scan) {
      return res.status(404).json({ error: 'Scan not found' });
    }

    res.json({
      scanId,
      status: scan.status,
      filesProcessed: scan.file_count || 0,
      progress: scan.status === 'COMPLETE' ? 100 : 0
    });
  } catch (error) {
    console.error('Error fetching scan status:', error);
    res.status(500).json({ error: 'Failed to fetch scan status' });
  }
});

export default router;
