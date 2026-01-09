/**
 * Inspection reports API routes
 * Provides access to pass reports and summaries
 */

import { Router, Request, Response } from 'express';
import { DatabaseService } from '../../services/DatabaseService';

const router = Router();
const db = new DatabaseService();

/**
 * GET /api/reports/:sessionId
 * Get all reports for an inspection session
 */
router.get('/:sessionId', async (req: Request, res: Response) => {
  try {
    const sessionId = parseInt(req.params.sessionId);

    const inspection = db.getInspection(sessionId);
    if (!inspection) {
      return res.status(404).json({ error: 'Inspection not found' });
    }

    const passes = db.getInspectionPasses(sessionId);
    const reports: Record<string, any> = {};

    for (const pass of passes) {
      if (pass.report_json) {
        try {
          reports[`pass${pass.pass_number}`] = JSON.parse(pass.report_json);
        } catch {
          reports[`pass${pass.pass_number}`] = { error: 'Failed to parse report' };
        }
      }
    }

    res.json({
      session_id: sessionId,
      inspection,
      reports
    });
  } catch (error) {
    console.error('Error fetching reports:', error);
    res.status(500).json({ error: 'Failed to fetch reports' });
  }
});

/**
 * GET /api/reports/:sessionId/pass/:passNumber
 * Get report for a specific pass
 */
router.get('/:sessionId/pass/:passNumber', async (req: Request, res: Response) => {
  try {
    const sessionId = parseInt(req.params.sessionId);
    const passNumber = parseInt(req.params.passNumber);

    const pass = db.getInspectionPass(sessionId, passNumber);
    if (!pass) {
      return res.status(404).json({ error: 'Pass not found' });
    }

    let report = null;
    if (pass.report_json) {
      try {
        report = JSON.parse(pass.report_json);
      } catch {
        report = { error: 'Failed to parse report' };
      }
    }

    res.json({
      session_id: sessionId,
      pass_number: passNumber,
      pass_name: pass.pass_name,
      status: pass.status,
      started_at: pass.started_at,
      completed_at: pass.completed_at,
      error_message: pass.error_message,
      report
    });
  } catch (error) {
    console.error('Error fetching pass report:', error);
    res.status(500).json({ error: 'Failed to fetch pass report' });
  }
});

/**
 * GET /api/reports/:sessionId/health
 * Get health report (Pass 1) summary
 */
router.get('/:sessionId/health', async (req: Request, res: Response) => {
  try {
    const sessionId = parseInt(req.params.sessionId);

    const pass = db.getInspectionPass(sessionId, 1);
    if (!pass || !pass.report_json) {
      return res.status(404).json({ error: 'Health report not available' });
    }

    const report = JSON.parse(pass.report_json);

    // Return a summary format suitable for the HealthReport component
    res.json({
      session_id: sessionId,
      drive_path: report.drive_path,
      drive_letter: report.drive_letter,
      inspection_time: report.inspection_time,
      overall_health: report.overall_health,
      health_score: report.health_score,
      chkdsk: report.chkdsk_result ? {
        success: report.chkdsk_result.success,
        filesystem_type: report.chkdsk_result.filesystem_type,
        errors_found: report.chkdsk_result.errors_found,
        bad_sectors: report.chkdsk_result.bad_sectors,
        execution_time: report.chkdsk_result.execution_time_seconds
      } : null,
      smart: report.smart_data ? {
        available: report.smart_data.available,
        health_status: report.smart_data.health_status,
        temperature: report.smart_data.temperature_celsius,
        power_on_hours: report.smart_data.power_on_hours,
        reallocated_sectors: report.smart_data.reallocated_sectors
      } : null,
      recommendations: report.recommendations,
      warnings: report.warnings,
      errors: report.errors,
      summary: report.summary
    });
  } catch (error) {
    console.error('Error fetching health report:', error);
    res.status(500).json({ error: 'Failed to fetch health report' });
  }
});

/**
 * GET /api/reports/:sessionId/os
 * Get OS detection report (Pass 2) summary
 */
router.get('/:sessionId/os', async (req: Request, res: Response) => {
  try {
    const sessionId = parseInt(req.params.sessionId);

    const pass = db.getInspectionPass(sessionId, 2);
    if (!pass || !pass.report_json) {
      return res.status(404).json({ error: 'OS report not available' });
    }

    const report = JSON.parse(pass.report_json);

    res.json({
      session_id: sessionId,
      drive_path: report.drive_path,
      drive_letter: report.drive_letter,
      inspection_time: report.inspection_time,
      os_type: report.os_type,
      os_name: report.os_name,
      version: report.version,
      build_number: report.build_number,
      edition: report.edition,
      install_date: report.install_date,
      boot_capable: report.boot_capable,
      detection_method: report.detection_method,
      confidence: report.confidence,
      user_profiles: report.user_profiles,
      windows_features: report.windows_features,
      installed_programs_count: report.installed_programs_count,
      recommendations: report.recommendations,
      warnings: report.warnings,
      errors: report.errors,
      summary: report.summary
    });
  } catch (error) {
    console.error('Error fetching OS report:', error);
    res.status(500).json({ error: 'Failed to fetch OS report' });
  }
});

/**
 * GET /api/reports/:sessionId/metadata
 * Get metadata report (Pass 3) summary
 */
router.get('/:sessionId/metadata', async (req: Request, res: Response) => {
  try {
    const sessionId = parseInt(req.params.sessionId);

    const pass = db.getInspectionPass(sessionId, 3);
    if (!pass || !pass.report_json) {
      return res.status(404).json({ error: 'Metadata report not available' });
    }

    const report = JSON.parse(pass.report_json);

    res.json({
      session_id: sessionId,
      total_files: report.total_files,
      total_folders: report.total_folders,
      total_size_bytes: report.total_size_bytes,
      files_hashed: report.files_hashed,
      duplicate_groups: report.duplicate_groups_found,
      total_duplicate_files: report.total_duplicate_files,
      wasted_bytes: report.total_wasted_bytes,
      cross_scan_duplicates: report.cross_scan_duplicates,
      extension_counts: report.extension_counts,
      size_distribution: report.size_distribution,
      oldest_file_date: report.oldest_file_date,
      newest_file_date: report.newest_file_date
    });
  } catch (error) {
    console.error('Error fetching metadata report:', error);
    res.status(500).json({ error: 'Failed to fetch metadata report' });
  }
});

/**
 * GET /api/reports/:sessionId/review
 * Get review report (Pass 4) with decision points
 */
router.get('/:sessionId/review', async (req: Request, res: Response) => {
  try {
    const sessionId = parseInt(req.params.sessionId);

    const pass = db.getInspectionPass(sessionId, 4);
    if (!pass || !pass.report_json) {
      return res.status(404).json({ error: 'Review report not available' });
    }

    const report = JSON.parse(pass.report_json);

    // Also get any decisions that have been made
    const decisions = db.getDecisions(sessionId);

    res.json({
      session_id: sessionId,
      drive_path: report.drive_path,
      drive_model: report.drive_model,
      drive_serial: report.drive_serial,
      health_summary: report.health_summary,
      os_summary: report.os_summary,
      metadata_summary: report.metadata_summary,
      decision_points: report.decision_points,
      resolved_decisions: decisions,
      recommendations: report.recommendations,
      warnings: report.warnings,
      report_path: report.report_path,
      summary: report.summary
    });
  } catch (error) {
    console.error('Error fetching review report:', error);
    res.status(500).json({ error: 'Failed to fetch review report' });
  }
});

/**
 * GET /api/reports/:sessionId/duplicates
 * Get duplicate file groups from metadata scan
 */
router.get('/:sessionId/duplicates', async (req: Request, res: Response) => {
  try {
    const sessionId = parseInt(req.params.sessionId);
    const limit = parseInt(req.query.limit as string) || 50;

    const duplicates = db.getDuplicateGroups(sessionId, limit);

    res.json({
      session_id: sessionId,
      groups: duplicates
    });
  } catch (error) {
    console.error('Error fetching duplicates:', error);
    res.status(500).json({ error: 'Failed to fetch duplicates' });
  }
});

export default router;
