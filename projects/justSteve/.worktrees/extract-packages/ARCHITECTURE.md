# Architecture Documentation

## Overview

The Wayback Archive Toolkit has been refactored to follow a **modular, package-based architecture** that separates reusable infrastructure from domain-specific logic.

## Directory Structure

```
/root/
├── packages/                       # Shared infrastructure tier
│   ├── api-server/                # @myorg/api-server
│   │   ├── src/
│   │   │   ├── server.ts         # Express app factory
│   │   │   ├── middleware/       # Error handling
│   │   │   └── routes/           # Health endpoint
│   │   ├── package.json
│   │   ├── tsconfig.json
│   │   └── README.md
│   │
│   └── dashboard-ui/              # @myorg/dashboard-ui
│       ├── src/
│       │   ├── components/       # InfoCard, etc.
│       │   ├── layouts/          # DashboardLayout
│       │   └── theme/            # Dark theme
│       ├── package.json
│       ├── tsconfig.json
│       └── README.md
│
└── projects/justSteve/            # Domain project tier
    ├── src/
    │   ├── domain/               # WBM business logic
    │   │   ├── cdx/             # CDX analysis
    │   │   │   └── CDXAnalyzerController.ts
    │   │   ├── crawler/         # Wayback crawler
    │   │   │   ├── WaybackCrawler.ts
    │   │   │   ├── WaybackAPIService.ts
    │   │   │   └── SnapshotSelector.ts
    │   │   ├── assets/          # Asset handling
    │   │   │   ├── AssetExtractor.ts
    │   │   │   ├── AssetFetcher.ts
    │   │   │   └── URLRewriter.ts
    │   │   └── models/          # Data models
    │   │       ├── types.ts
    │   │       └── AssetTypes.ts
    │   │
    │   ├── api/                 # API layer
    │   │   ├── routes/         # Domain-specific routes
    │   │   │   ├── domains.ts  # Domain queries
    │   │   │   ├── logs.ts     # Log viewing
    │   │   │   └── archive.ts  # Archive serving
    │   │   └── index.ts        # Uses @myorg/api-server
    │   │
    │   ├── frontend/           # UI layer
    │   │   ├── components/     # WBM-specific components
    │   │   ├── App.tsx        # Main app
    │   │   └── theme.ts       # Custom WBM theme
    │   │
    │   ├── cli/               # Command-line tools
    │   ├── services/          # Infrastructure services
    │   └── utils/             # Shared utilities
    │
    └── package.json           # Depends on @myorg/* packages
```

## Package Dependencies

### Development (file: protocol)

```json
{
  "dependencies": {
    "@myorg/api-server": "file:../../../../packages/api-server",
    "@myorg/dashboard-ui": "file:../../../../packages/dashboard-ui"
  }
}
```

### Production (when published)

```json
{
  "dependencies": {
    "@myorg/api-server": "^1.0.0",
    "@myorg/dashboard-ui": "^1.0.0"
  }
}
```

## Design Principles

### 1. Separation of Concerns

- **Infrastructure Tier** (`/root/packages/`): Reusable across projects
- **Domain Tier** (`/root/projects/`): Project-specific business logic

### 2. Domain-Driven Organization

The `src/domain/` folder organizes code by business capability:

- `cdx/` - CDX analysis and snapshot detection
- `crawler/` - Wayback Machine crawling logic
- `assets/` - Asset extraction and fetching
- `models/` - Core data models and types

### 3. Unopinionated Infrastructure

Shared packages provide infrastructure without imposing:
- Domain-specific logic
- UI layouts or themes
- Business rules

Each project can customize as needed.

### 4. File Protocol for Local Development

During development, packages use `file:` protocol:
- Fast iteration without publishing
- Immediate reflection of changes
- No npm registry required

## API Server Architecture

### Infrastructure Layer (@myorg/api-server)

Provides:
- Express server setup
- CORS configuration
- JSON body parsing
- Health check endpoint
- Error handling middleware

### Domain Layer (WBM)

Adds:
- Domain routes (`/api/domains`, `/api/logs`, `/archive`)
- Database queries
- Business logic
- File serving

### Usage Example

```typescript
import { createApiServer } from '@myorg/api-server';
import domainsRouter from './routes/domains';

const app = createApiServer({ dbPath: './cdx_analysis.db' });
app.use('/api', domainsRouter);
```

## Frontend Architecture

### Shared Components (@myorg/dashboard-ui)

Provides:
- `DashboardLayout` - AppBar + Container wrapper
- `InfoCard` - Generic information card
- `darkTheme` - Material-UI dark theme

### WBM-Specific UI

Implements:
- Custom theme with brand colors
- Navigation logic (dashboard/domain/logs)
- Domain-specific components (DomainPage, LogViewer, etc.)
- Integration with WBM API

## Migration Benefits

### For Wayback Archive Toolkit

✅ **Cleaner Structure**: Domain logic separated from infrastructure
✅ **Better Testability**: 117 tests passing
✅ **Maintainability**: Clear boundaries between layers
✅ **Type Safety**: Full TypeScript support throughout

### For Future Projects

✅ **Faster Setup**: Reuse API server and UI infrastructure
✅ **Consistency**: Standard patterns across projects
✅ **Flexibility**: Each project customizes as needed
✅ **Zero Config**: Pre-configured Express, CORS, health checks

## Testing

All layers are tested:

```bash
# Run all tests
npm test

# Build packages
cd /root/packages/api-server && npm run build
cd /root/packages/dashboard-ui && npm run build

# Build WBM
cd /root/projects/justSteve && npm run build
```

**Test Coverage:**
- 16 test suites
- 117 tests passing
- Domain logic, services, utils fully tested

## Future Expansion

### Adding New Projects

1. Create project in `/root/projects/new-project/`
2. Add dependencies:
   ```json
   {
     "dependencies": {
       "@myorg/api-server": "file:../../packages/api-server",
       "@myorg/dashboard-ui": "file:../../packages/dashboard-ui"
     }
   }
   ```
3. Use shared infrastructure:
   ```typescript
   import { createApiServer } from '@myorg/api-server';
   import { DashboardLayout } from '@myorg/dashboard-ui';
   ```

### Publishing Packages

When ready to publish to npm:

```bash
cd /root/packages/api-server
npm publish --access public

cd /root/packages/dashboard-ui
npm publish --access public
```

Then update projects to use versioned packages:
```json
{
  "dependencies": {
    "@myorg/api-server": "^1.0.0",
    "@myorg/dashboard-ui": "^1.0.0"
  }
}
```

## References

- [API Server README](/root/packages/api-server/README.md)
- [Dashboard UI README](/root/packages/dashboard-ui/README.md)
- [WBM README](./README.md)
