/**
 * File browsing API routes
 */

import { Router, Request, Response } from 'express';
import { DatabaseService } from '../../services/DatabaseService';

const router = Router();
const db = new DatabaseService();

/**
 * GET /api/files/:scanId
 * Get files for a scan with pagination
 */
router.get('/:scanId', async (req: Request, res: Response) => {
  try {
    const scanId = parseInt(req.params.scanId);
    const limit = parseInt(req.query.limit as string) || 1000;
    const offset = parseInt(req.query.offset as string) || 0;

    const files = db.getFiles(scanId, limit, offset);
    const totalCount = db.getFileCount(scanId);

    res.json({
      files,
      pagination: {
        limit,
        offset,
        total: totalCount,
        hasMore: offset + limit < totalCount
      }
    });
  } catch (error) {
    console.error('Error fetching files:', error);
    res.status(500).json({ error: 'Failed to fetch files' });
  }
});

/**
 * GET /api/files/:scanId/extensions/:ext
 * Search files by extension
 */
router.get('/:scanId/extensions/:ext', async (req: Request, res: Response) => {
  try {
    const scanId = parseInt(req.params.scanId);
    const extension = req.params.ext;
    const limit = parseInt(req.query.limit as string) || 100;

    const files = db.searchByExtension(scanId, extension, limit);

    res.json({
      extension,
      files,
      count: files.length
    });
  } catch (error) {
    console.error('Error searching files:', error);
    res.status(500).json({ error: 'Failed to search files' });
  }
});

export default router;
