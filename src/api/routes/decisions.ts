/**
 * Inspection decisions API routes
 * Records and retrieves user decisions during inspection review
 */

import { Router, Request, Response } from 'express';
import { DatabaseService } from '../../services/DatabaseService';

const router = Router();
const db = new DatabaseService();

/**
 * GET /api/decisions/:sessionId
 * Get all decisions for an inspection session
 */
router.get('/:sessionId', async (req: Request, res: Response) => {
  try {
    const sessionId = parseInt(req.params.sessionId);
    const decisions = db.getDecisions(sessionId);

    res.json({
      session_id: sessionId,
      decisions
    });
  } catch (error) {
    console.error('Error fetching decisions:', error);
    res.status(500).json({ error: 'Failed to fetch decisions' });
  }
});

/**
 * GET /api/decisions/:sessionId/pending
 * Get pending (unresolved) decision points
 */
router.get('/:sessionId/pending', async (req: Request, res: Response) => {
  try {
    const sessionId = parseInt(req.params.sessionId);

    // Get pass 4 report to find all decision points
    const pass = db.getInspectionPass(sessionId, 4);
    if (!pass || !pass.report_json) {
      return res.json({ session_id: sessionId, pending: [] });
    }

    const report = JSON.parse(pass.report_json);
    const allDecisionPoints = report.decision_points || [];

    // Get existing decisions
    const existingDecisions = db.getDecisions(sessionId);
    const resolvedIds = new Set(existingDecisions.map(d => d.decision_key));

    // Filter to pending
    const pending = allDecisionPoints.filter(
      (dp: any) => !resolvedIds.has(dp.decision_id)
    );

    res.json({
      session_id: sessionId,
      pending,
      resolved_count: existingDecisions.length,
      total_count: allDecisionPoints.length
    });
  } catch (error) {
    console.error('Error fetching pending decisions:', error);
    res.status(500).json({ error: 'Failed to fetch pending decisions' });
  }
});

/**
 * POST /api/decisions/:sessionId
 * Record a new decision
 */
router.post('/:sessionId', async (req: Request, res: Response) => {
  try {
    const sessionId = parseInt(req.params.sessionId);
    const { decisionType, decisionKey, decisionValue, description, decidedBy } = req.body;

    if (!decisionType || !decisionKey || !decisionValue) {
      return res.status(400).json({
        error: 'decisionType, decisionKey, and decisionValue are required'
      });
    }

    const decisionId = db.recordDecision(
      sessionId,
      decisionType,
      decisionKey,
      decisionValue,
      description,
      decidedBy || 'user'
    );

    console.log(`[API] Recorded decision ${decisionId}: ${decisionType}=${decisionValue}`);

    res.json({
      success: true,
      decision_id: decisionId,
      session_id: sessionId,
      decision_type: decisionType,
      decision_key: decisionKey,
      decision_value: decisionValue
    });
  } catch (error) {
    console.error('Error recording decision:', error);
    res.status(500).json({ error: 'Failed to record decision' });
  }
});

/**
 * POST /api/decisions/:sessionId/batch
 * Record multiple decisions at once
 */
router.post('/:sessionId/batch', async (req: Request, res: Response) => {
  try {
    const sessionId = parseInt(req.params.sessionId);
    const { decisions } = req.body;

    if (!Array.isArray(decisions) || decisions.length === 0) {
      return res.status(400).json({ error: 'decisions array is required' });
    }

    const results: number[] = [];

    for (const decision of decisions) {
      const decisionId = db.recordDecision(
        sessionId,
        decision.decisionType,
        decision.decisionKey,
        decision.decisionValue,
        decision.description,
        decision.decidedBy || 'user'
      );
      results.push(decisionId);
    }

    console.log(`[API] Recorded ${results.length} decisions for session ${sessionId}`);

    res.json({
      success: true,
      session_id: sessionId,
      decision_ids: results,
      count: results.length
    });
  } catch (error) {
    console.error('Error recording batch decisions:', error);
    res.status(500).json({ error: 'Failed to record decisions' });
  }
});

/**
 * DELETE /api/decisions/:sessionId/:decisionId
 * Delete a decision (for corrections)
 */
router.delete('/:sessionId/:decisionId', async (req: Request, res: Response) => {
  try {
    const sessionId = parseInt(req.params.sessionId);
    const decisionId = parseInt(req.params.decisionId);

    const success = db.deleteDecision(sessionId, decisionId);

    if (!success) {
      return res.status(404).json({ error: 'Decision not found' });
    }

    res.json({
      success: true,
      deleted_decision_id: decisionId
    });
  } catch (error) {
    console.error('Error deleting decision:', error);
    res.status(500).json({ error: 'Failed to delete decision' });
  }
});

export default router;
