/**
 * API Server Entry Point
 * Uses @myorg/api-server for infrastructure
 */

import { createApiServer, startServer } from '@myorg/api-server';
import scansRouter from './routes/scans';
import drivesRouter from './routes/drives';
import filesRouter from './routes/files';

// Create server with shared infrastructure
const app = createApiServer({
  dbPath: './output/archive.db',
  enableLogging: true
});

// Add domain-specific routes
app.use('/api/scans', scansRouter);
app.use('/api/drives', drivesRouter);
app.use('/api/files', filesRouter);

// Start server
const PORT = process.env.PORT ? parseInt(process.env.PORT) : 3001;
startServer(app, PORT);

console.log('DataArchive API Server');
console.log('======================');
console.log(`API:      http://localhost:${PORT}`);
console.log(`Health:   http://localhost:${PORT}/api/health`);
console.log(`Frontend: http://localhost:5173 (run 'npm run dev')`);
