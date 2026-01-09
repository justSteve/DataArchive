/**
 * Drive discovery and information API routes
 */

import { Router, Request, Response } from 'express';
import { DatabaseService } from '../../services/DatabaseService';
import { PythonBridge } from '../../services/PythonBridge';

const router = Router();
const db = new DatabaseService();
const bridge = new PythonBridge();

/**
 * GET /api/drives
 * List all known drives
 */
router.get('/', async (req: Request, res: Response) => {
  try {
    const drives = db.getDrives();
    res.json(drives);
  } catch (error) {
    console.error('Error fetching drives:', error);
    res.status(500).json({ error: 'Failed to fetch drives' });
  }
});

/**
 * POST /api/drives/validate
 * Validate a drive path before scanning
 */
router.post('/validate', async (req: Request, res: Response) => {
  try {
    const { drivePath } = req.body;

    if (!drivePath) {
      return res.status(400).json({ error: 'drivePath is required' });
    }

    const validation = await bridge.validateDrive(drivePath);

    res.json(validation);
  } catch (error) {
    console.error('Error validating drive:', error);
    res.status(500).json({ error: 'Failed to validate drive' });
  }
});

/**
 * POST /api/drives/info
 * Get hardware information for a drive
 */
router.post('/info', async (req: Request, res: Response) => {
  try {
    const { drivePath } = req.body;

    if (!drivePath) {
      return res.status(400).json({ error: 'drivePath is required' });
    }

    const info = await bridge.getDriveInfo(drivePath);

    res.json(info);
  } catch (error) {
    console.error('Error getting drive info:', error);
    res.status(500).json({ error: 'Failed to get drive info' });
  }
});

export default router;
