import { Router, Request, Response } from 'express';
import * as fs from 'fs';
import { ServerOptions } from '../server';

/**
 * Health check endpoint
 */
export function healthRouter(options: ServerOptions = {}): Router {
  const router = Router();

  router.get('/', (_req: Request, res: Response) => {
    const health = {
      status: 'ok',
      timestamp: new Date().toISOString(),
      uptime: process.uptime(),
      ...(options.dbPath && {
        database: fs.existsSync(options.dbPath)
      })
    };

    res.json(health);
  });

  return router;
}
