/**
 * Log streaming API routes
 */

import { Router, Request, Response } from 'express';
import { logStream } from '../../services/LogStream';

const router = Router();

/**
 * GET /api/logs/stream
 * Server-Sent Events (SSE) endpoint for real-time logs
 */
router.get('/stream', (req: Request, res: Response) => {
  console.log('[Logs] Client connected to log stream');
  logStream.addClient(res);
});

/**
 * GET /api/logs/recent
 * Get recent logs (fallback for clients that don't support SSE)
 */
router.get('/recent', (req: Request, res: Response) => {
  const count = parseInt(req.query.count as string) || 100;
  const logs = logStream.getRecentLogs(count);
  res.json({ logs });
});

/**
 * DELETE /api/logs
 * Clear log buffer
 */
router.delete('/', (req: Request, res: Response) => {
  logStream.clearLogs();
  console.log('[Logs] Log buffer cleared');
  res.json({ success: true, message: 'Logs cleared' });
});

/**
 * GET /api/logs/stats
 * Get log stream statistics
 */
router.get('/stats', (req: Request, res: Response) => {
  res.json({
    connected_clients: logStream.getClientCount()
  });
});

export default router;
