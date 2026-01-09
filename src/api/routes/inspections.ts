/**
 * Inspection workflow API routes
 * Manages multi-pass drive inspection workflow
 */

import { Router, Request, Response } from 'express';
import { DatabaseService } from '../../services/DatabaseService';
import { PythonBridge } from '../../services/PythonBridge';

const router = Router();
const db = new DatabaseService();
const bridge = new PythonBridge();

/**
 * GET /api/inspections
 * List all inspections (with optional status filter)
 */
router.get('/', async (req: Request, res: Response) => {
  try {
    const status = req.query.status as string | undefined;
    const limit = parseInt(req.query.limit as string) || 20;

    const inspections = db.getInspections(limit, status);
    res.json(inspections);
  } catch (error) {
    console.error('Error fetching inspections:', error);
    res.status(500).json({ error: 'Failed to fetch inspections' });
  }
});

/**
 * GET /api/inspections/active
 * Get active inspections
 */
router.get('/active', async (req: Request, res: Response) => {
  try {
    const inspections = db.getActiveInspections();
    res.json(inspections);
  } catch (error) {
    console.error('Error fetching active inspections:', error);
    res.status(500).json({ error: 'Failed to fetch active inspections' });
  }
});

/**
 * GET /api/inspections/:id
 * Get a specific inspection with all passes
 */
router.get('/:id', async (req: Request, res: Response) => {
  try {
    const sessionId = parseInt(req.params.id);
    const inspection = db.getInspection(sessionId);

    if (!inspection) {
      return res.status(404).json({ error: 'Inspection not found' });
    }

    res.json(inspection);
  } catch (error) {
    console.error('Error fetching inspection:', error);
    res.status(500).json({ error: 'Failed to fetch inspection' });
  }
});

/**
 * POST /api/inspections/start
 * Start a new inspection workflow
 */
router.post('/start', async (req: Request, res: Response) => {
  try {
    const { drivePath, beadsIssueId } = req.body;

    if (!drivePath) {
      return res.status(400).json({ error: 'drivePath is required' });
    }

    console.log(`[API] Starting inspection for: ${drivePath}`);

    // Validate and get drive info
    const validation = await bridge.validateDrive(drivePath);
    if (!validation.valid) {
      return res.status(400).json({
        error: 'Drive validation failed',
        validation
      });
    }

    // Get drive hardware info
    const driveInfo = await bridge.getDriveInfo(drivePath);
    console.log(`[API] Drive detected: ${driveInfo.model} (SN: ${driveInfo.serial_number})`);

    // Create or get drive record
    const driveId = db.upsertDrive(driveInfo);

    // Start inspection session
    const sessionId = db.startInspection(driveId, beadsIssueId);
    console.log(`[API] Created inspection session ${sessionId}`);

    res.json({
      success: true,
      session_id: sessionId,
      drive_info: driveInfo,
      status: 'active',
      current_pass: 1
    });
  } catch (error) {
    console.error('Error starting inspection:', error);
    res.status(500).json({
      error: 'Failed to start inspection',
      message: error instanceof Error ? error.message : String(error)
    });
  }
});

/**
 * POST /api/inspections/:id/pass/:passNumber/start
 * Start a specific pass
 */
router.post('/:id/pass/:passNumber/start', async (req: Request, res: Response) => {
  try {
    const sessionId = parseInt(req.params.id);
    const passNumber = parseInt(req.params.passNumber);

    if (passNumber < 1 || passNumber > 4) {
      return res.status(400).json({ error: 'Pass number must be 1-4' });
    }

    const inspection = db.getInspection(sessionId);
    if (!inspection) {
      return res.status(404).json({ error: 'Inspection not found' });
    }

    // Mark pass as started
    db.startPass(sessionId, passNumber);

    // For passes 1-3, run Python script in background
    const drivePath = inspection.mount_point || '/mnt/c';

    if (passNumber <= 3) {
      // Execute the appropriate Python pass script
      bridge.runInspectionPass(sessionId, passNumber, drivePath)
        .then(() => {
          console.log(`[API] Pass ${passNumber} completed for session ${sessionId}`);
        })
        .catch(error => {
          console.error(`[API] Pass ${passNumber} failed:`, error);
          db.failPass(sessionId, passNumber, error.message);
        });
    }

    res.json({
      success: true,
      session_id: sessionId,
      pass_number: passNumber,
      status: 'running'
    });
  } catch (error) {
    console.error('Error starting pass:', error);
    res.status(500).json({
      error: 'Failed to start pass',
      message: error instanceof Error ? error.message : String(error)
    });
  }
});

/**
 * POST /api/inspections/:id/pass/:passNumber/skip
 * Skip a specific pass
 */
router.post('/:id/pass/:passNumber/skip', async (req: Request, res: Response) => {
  try {
    const sessionId = parseInt(req.params.id);
    const passNumber = parseInt(req.params.passNumber);
    const { reason } = req.body;

    db.skipPass(sessionId, passNumber, reason || 'Skipped by user');

    res.json({
      success: true,
      session_id: sessionId,
      pass_number: passNumber,
      status: 'skipped'
    });
  } catch (error) {
    console.error('Error skipping pass:', error);
    res.status(500).json({ error: 'Failed to skip pass' });
  }
});

/**
 * POST /api/inspections/:id/complete
 * Complete an inspection session
 */
router.post('/:id/complete', async (req: Request, res: Response) => {
  try {
    const sessionId = parseInt(req.params.id);
    const { status } = req.body;

    db.completeInspection(sessionId, status || 'completed');

    res.json({
      success: true,
      session_id: sessionId,
      status: status || 'completed'
    });
  } catch (error) {
    console.error('Error completing inspection:', error);
    res.status(500).json({ error: 'Failed to complete inspection' });
  }
});

/**
 * GET /api/inspections/:id/passes
 * Get all passes for an inspection
 */
router.get('/:id/passes', async (req: Request, res: Response) => {
  try {
    const sessionId = parseInt(req.params.id);
    const passes = db.getInspectionPasses(sessionId);
    res.json(passes);
  } catch (error) {
    console.error('Error fetching passes:', error);
    res.status(500).json({ error: 'Failed to fetch passes' });
  }
});

export default router;
