/**
 * @myorg/api-server
 *
 * Shared API server boilerplate with Express, CORS, and health endpoints
 */

export { createApiServer, startServer, ServerOptions } from './server';
export { errorHandler } from './middleware/errorHandler';
export { healthRouter } from './routes/health';
