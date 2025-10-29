# @myorg/api-server

Shared API server boilerplate with Express, CORS, and standard middleware.

## Features

- ✅ Pre-configured Express server with CORS
- ✅ JSON body parsing
- ✅ Health check endpoint (`/api/health`)
- ✅ Centralized error handling
- ✅ Optional request logging
- ✅ TypeScript support with full type definitions

## Installation

### Local Development (file: protocol)

```json
{
  "dependencies": {
    "@myorg/api-server": "file:../../packages/api-server"
  }
}
```

### Published Package (when published to npm)

```json
{
  "dependencies": {
    "@myorg/api-server": "^1.0.0"
  }
}
```

## Usage

### Basic Setup

```typescript
import { createApiServer, startServer } from '@myorg/api-server';

// Create server with infrastructure
const app = createApiServer({
  dbPath: './database.db',
  enableLogging: true
});

// Add your domain-specific routes
app.use('/api/users', usersRouter);
app.use('/api/posts', postsRouter);

// Start server
startServer(app, 3001);
```

### With Custom Options

```typescript
import { createApiServer } from '@myorg/api-server';

const app = createApiServer({
  // Optional: database path for health check
  dbPath: process.env.DB_PATH,

  // Optional: enable request logging
  enableLogging: process.env.NODE_ENV === 'development',

  // Optional: custom CORS configuration
  corsOptions: {
    origin: 'https://yourdomain.com',
    credentials: true
  }
});
```

## API Reference

### `createApiServer(options?): Express`

Creates a pre-configured Express server with standard middleware.

**Options:**
- `dbPath?: string` - Path to database file for health check
- `enableLogging?: boolean` - Enable request logging (default: false)
- `corsOptions?: cors.CorsOptions` - Custom CORS configuration

**Returns:** Express application instance

**Includes:**
- CORS middleware (all origins by default)
- JSON body parser
- Health check endpoint at `/api/health`
- Error handling middleware

### `startServer(app, port?): void`

Starts the Express server on the specified port.

**Parameters:**
- `app: Express` - Express application instance
- `port?: number` - Port number (default: 3001)

## Health Check Endpoint

The package automatically adds a health check endpoint:

```
GET /api/health
```

**Response:**
```json
{
  "status": "ok",
  "timestamp": "2025-10-19T21:00:00.000Z",
  "uptime": 123.456,
  "database": true  // Only if dbPath provided
}
```

## Development

### Building

```bash
npm run build
```

### Watching

```bash
npm run watch
```

### Cleaning

```bash
npm run clean
```

## License

MIT
