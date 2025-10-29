import express, { Express, Request, Response, NextFunction } from 'express';
import cors from 'cors';
import { healthRouter } from './routes/health';
import { errorHandler } from './middleware/errorHandler';

export interface ServerOptions {
  /**
   * Path to database file for health check
   */
  dbPath?: string;

  /**
   * Custom CORS options
   */
  corsOptions?: cors.CorsOptions;

  /**
   * Enable request logging
   */
  enableLogging?: boolean;
}

/**
 * Create a pre-configured Express server with standard middleware
 */
export function createApiServer(options: ServerOptions = {}): any {
  const app = express();

  // CORS - allow all origins by default
  app.use(cors(options.corsOptions));

  // Parse JSON bodies
  app.use(express.json());

  // Optional request logging
  if (options.enableLogging) {
    app.use((req: Request, _res: Response, next: NextFunction) => {
      console.log(`${new Date().toISOString()} ${req.method} ${req.path}`);
      next();
    });
  }

  // Health check endpoint
  app.use('/api/health', healthRouter(options));

  // Error handling middleware (must be last)
  app.use(errorHandler);

  return app;
}

/**
 * Start the server on specified port
 */
export function startServer(app: any, port = 3001): void {
  app.listen(port, () => {
    console.log(`API server running on http://localhost:${port}`);
  });
}
