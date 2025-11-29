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
 * Start a new scan (NON-BLOCKING - returns immediately)
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

    // Get real hardware info BEFORE creating scan
    console.log(`[API] Getting hardware info for: ${drivePath}`);
    const driveInfo = await bridge.getDriveInfo(drivePath);
    console.log(`[API] Drive detected: ${driveInfo.model} (SN: ${driveInfo.serial_number})`);

    // Check for recent scans of this drive
    const recentScans = db.getScans(100).filter(
      scan => scan.serial_number === driveInfo.serial_number
    );

    if (recentScans.length > 0) {
      const lastScan = recentScans[0];
      const lastScanDate = new Date(lastScan.scan_start);
      const hoursSinceLastScan = (Date.now() - lastScanDate.getTime()) / (1000 * 60 * 60);

      console.log(`[API] Warning: Drive ${driveInfo.serial_number} was last scanned ${hoursSinceLastScan.toFixed(1)} hours ago`);

      // Return warning (but allow scan to proceed)
      if (hoursSinceLastScan < 24) {
        return res.status(409).json({
          error: 'Drive recently scanned',
          warning: `This drive was scanned ${hoursSinceLastScan.toFixed(1)} hours ago`,
          last_scan: lastScan,
          drive_info: driveInfo,
          can_proceed: true
        });
      }
    }

    // Create drive and scan records in database
    console.log(`[API] Creating scan record for: ${drivePath}`);
    const driveId = db.upsertDrive(driveInfo);
    const scanId = db.createScan(driveId, drivePath);
    console.log(`[API] Created scan ${scanId} for drive ${driveId}`);

    // Start scan in background (non-blocking)
    console.log(`[API] Starting async scan ${scanId}: ${drivePath}`);
    bridge.scanDriveAsync(scanId, drivePath, defaultDbPath, {
      ...options,
      driveModel: driveInfo.model,
      driveSerial: driveInfo.serial_number
    })
      .catch(error => {
        console.error(`[API] Scan ${scanId} failed:`, error);
        // Mark scan as failed in database
        db.cancelScan(scanId);
      });

    // Return immediately with scan_id
    res.json({
      success: true,
      scan_id: scanId,
      drive_info: driveInfo,
      status: 'IN_PROGRESS'
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
 * POST /api/scans/:id/cancel
 * Cancel a running scan
 */
router.post('/:id/cancel', async (req: Request, res: Response) => {
  try {
    const scanId = parseInt(req.params.id);

    console.log(`[API] Cancelling scan ${scanId}`);
    const cancelled = bridge.cancelScan(scanId);

    if (cancelled) {
      // Update database status
      db.cancelScan(scanId);
      res.json({
        success: true,
        message: `Scan ${scanId} cancelled`
      });
    } else {
      res.status(404).json({
        error: 'Scan not found or not running',
        scanId
      });
    }
  } catch (error) {
    console.error('Error cancelling scan:', error);
    res.status(500).json({
      error: 'Failed to cancel scan',
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
