/**
 * API Server Entry Point
 * Uses @myorg/api-server for infrastructure
 */

import { createApiServer, startServer } from '@myorg/api-server';
import scansRouter from './routes/scans';
import drivesRouter from './routes/drives';
import filesRouter from './routes/files';
import logsRouter from './routes/logs';
import adminRouter from './routes/admin';
import { logStream } from '../services/LogStream';

// Initialize log stream (starts capturing console logs)
logStream;

// Create server with shared infrastructure
const app = createApiServer({
  dbPath: './output/archive.db',
  enableLogging: true
});

// Add domain-specific routes
app.use('/api/scans', scansRouter);
app.use('/api/drives', drivesRouter);
app.use('/api/files', filesRouter);
app.use('/api/logs', logsRouter);
app.use('/api/admin', adminRouter);

// Start server
const PORT = process.env.PORT ? parseInt(process.env.PORT) : 3001;
startServer(app, PORT);

console.log('DataArchive API Server');
console.log('======================');
console.log(`API:      http://localhost:${PORT}`);
console.log(`Health:   http://localhost:${PORT}/api/health`);
console.log(`Frontend: http://localhost:5173 (run 'npm run dev')`);
