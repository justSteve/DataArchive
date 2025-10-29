# Enterprise Architecture Blueprint
## Pattern for Building Domain Projects with Shared Infrastructure

**Version:** 1.0
**Date:** October 2025
**Context:** Lessons learned from refactoring the Wayback Archive Toolkit

---

## Table of Contents

1. [Vision & Motivations](#vision--motivations)
2. [Architecture Pattern](#architecture-pattern)
3. [Shared Infrastructure Packages](#shared-infrastructure-packages)
4. [Domain Project Structure](#domain-project-structure)
5. [Migration Playbook](#migration-playbook)
6. [Bootstrapping New Projects](#bootstrapping-new-projects)
7. [Best Practices](#best-practices)
8. [Reference Implementation](#reference-implementation)

---

## Vision & Motivations

### The Problem

Building multiple independent projects that share a common pattern:

1. **Domain-Specific Logic**: Each project solves a unique problem (e.g., archive retrieval, data processing, credential management)
2. **Common Infrastructure Needs**: Every project needs:
   - API server with CORS, health checks, error handling
   - Web dashboard to operate and display results
   - Standard middleware and utilities
3. **Repeated Boilerplate**: Without shared infrastructure, each project reimplements the same foundation

### The Insight

**Projects in our enterprise follow a pattern:**
- A problem to be solved (the domain logic)
- A webapp that operates the code and displays output (the interface)
- Standard infrastructure needs (API, UI, database, logging)

**The solution:**
- Extract **infrastructure** into shared packages (reusable foundation)
- Keep **domain logic** project-specific (unique business value)
- Use **file:// protocol** for fast local development iteration

### Goals

✅ **Reduce Duplication**: Write infrastructure code once, reuse everywhere
✅ **Faster Setup**: New projects start with working API and UI
✅ **Consistency**: Standard patterns across all enterprise projects
✅ **Flexibility**: Each project customizes for its specific needs
✅ **Maintainability**: Update infrastructure once, benefit all projects

---

## Architecture Pattern

### Two-Tier Structure

```
/root/
├── packages/              # INFRASTRUCTURE TIER
│   ├── api-server/       # Shared API boilerplate
│   ├── dashboard-ui/     # Shared UI components
│   └── [future-shared]/  # Other shared packages
│
└── projects/              # DOMAIN TIER
    ├── project-a/        # First domain project
    ├── project-b/        # Second domain project
    └── project-n/        # Nth domain project
```

### Key Principles

1. **Infrastructure Tier** (`/root/packages/`)
   - Contains NO domain-specific logic
   - Provides unopinionated foundations
   - Reusable across ALL projects
   - Published as npm packages (or private registry)

2. **Domain Tier** (`/root/projects/`)
   - Contains ALL business logic
   - Consumes infrastructure packages
   - Organized by domain capability
   - Independent deployment

3. **Dependency Direction**
   - Domain projects → depend on → Infrastructure packages
   - Infrastructure packages → NEVER depend on → Domain projects
   - Infrastructure packages → MAY depend on → other infrastructure packages

---

## Shared Infrastructure Packages

### Package: @myorg/api-server

**Purpose:** Express API server boilerplate

**Provides:**
- Pre-configured Express application
- CORS middleware (configurable)
- JSON body parsing
- Health check endpoint (`/api/health`)
- Centralized error handling
- Optional request logging

**Does NOT provide:**
- Business logic
- Database schemas
- Domain routes
- Authentication (project-specific)

**Usage:**
```typescript
import { createApiServer } from '@myorg/api-server';

const app = createApiServer({
  dbPath: './my-database.db',
  enableLogging: true
});

// Add domain-specific routes
app.use('/api/users', usersRouter);
app.use('/api/widgets', widgetsRouter);

startServer(app, 3001);
```

**When to use:**
- Every project with an API backend
- When you need REST endpoints
- When you want standard health checks

**When NOT to use:**
- Pure CLI-only projects
- Projects using GraphQL exclusively
- Serverless functions (different pattern)

---

### Package: @myorg/dashboard-ui

**Purpose:** React dashboard UI framework

**Provides:**
- Material-UI dark theme
- `DashboardLayout` component (AppBar + Container)
- `InfoCard` component (generic info display)
- Pre-configured TypeScript + React setup

**Does NOT provide:**
- Domain-specific components
- Business logic
- API integration
- Routing (project-specific)

**Usage:**
```typescript
import { DashboardLayout } from '@myorg/dashboard-ui';

function App() {
  return (
    <DashboardLayout title="My Project">
      <Grid container spacing={3}>
        {/* Your domain components */}
      </Grid>
    </DashboardLayout>
  );
}
```

**When to use:**
- Projects with web dashboard
- React-based frontends
- When you want consistent UI

**When NOT to use:**
- CLI-only projects
- Projects using different frameworks (Vue, Angular)
- Custom layout requirements (can still use theme)

---

## Domain Project Structure

### Recommended Organization

```
projects/my-project/
├── src/
│   ├── domain/              # Business logic (organized by capability)
│   │   ├── [capability-a]/  # e.g., user-management
│   │   ├── [capability-b]/  # e.g., data-processing
│   │   └── models/          # Domain models and types
│   │
│   ├── api/                 # API layer (uses @myorg/api-server)
│   │   ├── routes/         # Domain-specific routes
│   │   └── index.ts        # Server setup
│   │
│   ├── frontend/           # UI layer (uses @myorg/dashboard-ui)
│   │   ├── components/     # Domain-specific components
│   │   └── App.tsx        # Main app
│   │
│   ├── cli/               # Command-line tools
│   ├── services/          # Infrastructure services (DB, logging)
│   └── utils/             # Shared utilities
│
├── package.json           # Depends on @myorg/* packages
├── tsconfig.json
└── README.md
```

### The `/src/domain/` Folder

**Purpose:** Contains ALL domain-specific business logic

**Organize by capability, not technical layer:**
- ✅ `domain/user-management/`
- ✅ `domain/data-processing/`
- ✅ `domain/reporting/`
- ❌ `domain/controllers/`
- ❌ `domain/services/`

**Each capability folder contains:**
- Business logic implementations
- Domain-specific models
- Tests for that capability
- README explaining the capability

**Example (Wayback Archive Toolkit):**
```
domain/
├── cdx/              # CDX analysis capability
│   ├── CDXAnalyzerController.ts
│   └── __tests__/
├── crawler/          # Crawling capability
│   ├── WaybackCrawler.ts
│   ├── SnapshotSelector.ts
│   └── __tests__/
├── assets/           # Asset handling capability
│   ├── AssetExtractor.ts
│   └── __tests__/
└── models/           # Shared domain models
    └── types.ts
```

---

## Migration Playbook

### When to Apply This Pattern

**Good candidates:**
- Existing monolithic projects
- New projects in the enterprise
- Projects that duplicate infrastructure code

**Not recommended for:**
- Single-use scripts
- Experimental prototypes
- Projects with unique infrastructure needs

### 5-Phase Migration Approach

#### Phase 1: Create Package Scaffolding

**Goal:** Set up shared infrastructure packages

**Steps:**
1. Create `/root/packages/` directory
2. Create `api-server/` package:
   ```bash
   mkdir -p /root/packages/api-server/src/{middleware,routes}
   npm init -y
   npm install express cors
   npm install -D typescript @types/express @types/cors
   ```
3. Create `dashboard-ui/` package:
   ```bash
   mkdir -p /root/packages/dashboard-ui/src/{components,layouts,theme}
   npm init -y
   npm install @mui/material @emotion/react @emotion/styled
   ```
4. Build both packages to verify

**Success criteria:**
- Both packages build without errors
- Type definitions generated
- No circular dependencies

---

#### Phase 2: Extract API Server Boilerplate

**Goal:** Move generic API infrastructure to shared package

**What to extract:**
- Express setup
- CORS configuration
- JSON body parsing
- Health check endpoint
- Error handling middleware

**What to keep in project:**
- Domain-specific routes
- Database queries
- Business logic
- Authentication logic

**Steps:**
1. Add dependency to domain project:
   ```json
   "@myorg/api-server": "file:../../packages/api-server"
   ```
2. Create domain routes in `src/api/routes/`
3. Refactor server setup to use `createApiServer()`
4. Run tests to verify nothing broke

**Success criteria:**
- All tests passing
- API endpoints still work
- Health check responds correctly

---

#### Phase 3: Reorganize Domain Code

**Goal:** Clean separation of domain logic from infrastructure

**Steps:**
1. Create `src/domain/` structure
2. Move business logic to capability folders:
   ```bash
   git mv src/controllers/UserController.ts src/domain/user-management/
   git mv src/services/DataProcessor.ts src/domain/data-processing/
   ```
3. Update all imports
4. Run tests to verify

**Success criteria:**
- All tests passing
- Clear domain boundaries
- No circular dependencies
- Infrastructure services remain in `src/services/`

---

#### Phase 4: Extract Dashboard UI

**Goal:** Make shared UI components available

**What to extract:**
- Generic theme
- Layout components
- Reusable cards/widgets

**What to keep in project:**
- Domain-specific components
- Business logic in components
- Custom layouts

**Steps:**
1. Add dependency to domain project:
   ```json
   "@myorg/dashboard-ui": "file:../../packages/dashboard-ui"
   ```
2. Document availability in code comments
3. (Optional) Refactor to use shared components

**Success criteria:**
- Frontend builds successfully
- Shared package available for use
- Domain components remain project-specific

---

#### Phase 5: Documentation & Polish

**Goal:** Comprehensive documentation for future use

**Deliverables:**
1. **Package READMEs**: API reference for each package
2. **Project README**: Updated with new structure
3. **ARCHITECTURE.md**: Design decisions and patterns
4. **This Blueprint**: For future projects

**Success criteria:**
- Clear setup instructions
- API documentation complete
- Architecture decisions documented
- Future developers can bootstrap new projects

---

## Bootstrapping New Projects

### Starting from Scratch

**Step 1: Create Project Directory**
```bash
mkdir -p /root/projects/new-project
cd /root/projects/new-project
npm init -y
```

**Step 2: Add Shared Packages**
```json
{
  "dependencies": {
    "@myorg/api-server": "file:../../packages/api-server",
    "@myorg/dashboard-ui": "file:../../packages/dashboard-ui"
  }
}
```

**Step 3: Create Domain Structure**
```bash
mkdir -p src/domain/{capability-name,models}
mkdir -p src/api/routes
mkdir -p src/frontend/components
mkdir -p src/cli
```

**Step 4: Set Up API Server**

Create `src/api/index.ts`:
```typescript
import { createApiServer } from '@myorg/api-server';
import myRouter from './routes/my-routes';

const app = createApiServer({
  dbPath: './database.db',
  enableLogging: true
});

app.use('/api/my-resource', myRouter);

export default app;
```

**Step 5: Set Up Frontend**

Create `src/frontend/App.tsx`:
```typescript
import { DashboardLayout } from '@myorg/dashboard-ui';
import { Grid } from '@mui/material';
import MyComponent from './components/MyComponent';

function App() {
  return (
    <DashboardLayout title="My Project">
      <Grid container spacing={3}>
        <Grid item xs={12}>
          <MyComponent />
        </Grid>
      </Grid>
    </DashboardLayout>
  );
}
```

**Step 6: Install and Build**
```bash
npm install --legacy-peer-deps
npm run build
npm test
```

### Template Project Structure

**Use the Wayback Archive Toolkit as a template:**
```bash
# Copy structure (not content)
cp -r /root/projects/justSteve/src /root/projects/new-project/
# Remove WBM-specific domain logic
rm -rf /root/projects/new-project/src/domain/*
# Keep infrastructure
# Modify package.json, README.md
```

---

## Best Practices

### Package Development

1. **Keep packages small and focused**
   - api-server: Just Express infrastructure
   - dashboard-ui: Just React/MUI foundation
   - Don't create mega-packages

2. **Avoid domain logic in packages**
   - ❌ `getUserById()` in api-server
   - ✅ `errorHandler()` middleware in api-server

3. **Document with examples**
   - Every exported function has JSDoc
   - README has usage examples
   - Include TypeScript types

4. **Version carefully**
   - Use semantic versioning
   - Document breaking changes
   - Test before publishing

### Domain Project Development

1. **Organize by capability, not layer**
   - ✅ `domain/user-management/`
   - ❌ `domain/controllers/`

2. **Keep domain code DRY within project**
   - Extract common patterns
   - Use shared utilities
   - But don't over-abstract

3. **Tests co-located with code**
   - `domain/crawler/__tests__/`
   - Not `tests/domain/crawler/`

4. **Clear dependency boundaries**
   - Domain → uses → Infrastructure packages
   - Domain → NEVER → other domain projects

### File Protocol Development

1. **Fast iteration**
   - Changes in packages reflect immediately
   - No publish/install cycle
   - Great for development

2. **Build packages first**
   - Always build shared packages before domain project
   - Set up watch mode: `npm run watch`

3. **Correct relative paths**
   - From worktree: `file:../../../../packages/api-server`
   - From main: `file:../../packages/api-server`
   - Test with: `npm install`

4. **Switch to versions for production**
   - Development: `file:../../packages/api-server`
   - Production: `^1.0.0`

### Testing Strategy

1. **Test at all levels**
   - Unit tests: Individual functions
   - Integration tests: API endpoints
   - E2E tests: Full workflows

2. **Shared packages must have tests**
   - api-server: Test middleware, health endpoint
   - dashboard-ui: Test component rendering

3. **Domain projects test business logic**
   - Test domain capabilities
   - Test API routes
   - Test UI components

4. **Keep tests fast**
   - Mock external services
   - Use in-memory databases for tests
   - Run in parallel when possible

---

## Reference Implementation

### Wayback Archive Toolkit

**Project:** Multi-domain Wayback Machine archiver
**Location:** `/root/projects/justSteve`

**What it demonstrates:**

✅ **Shared Packages:**
- Uses `@myorg/api-server` for API infrastructure
- References `@myorg/dashboard-ui` (documented, not enforced)

✅ **Domain Organization:**
```
domain/
├── cdx/          # CDX analysis capability
├── crawler/      # Wayback crawling capability
├── assets/       # Asset handling capability
└── models/       # Domain models
```

✅ **API Layer:**
- Uses `createApiServer()` from shared package
- Domain routes: `/api/domains`, `/api/logs`, `/archive`
- Database-specific queries stay in project

✅ **Frontend:**
- Custom theme (domain-specific branding)
- Custom navigation (dashboard/domain/logs views)
- Shared components available but not mandatory

✅ **Tests:**
- 117 tests passing
- Domain logic fully tested
- Infrastructure tested separately

### Key Files to Reference

1. **Shared Package Setup:**
   - `/root/packages/api-server/src/server.ts`
   - `/root/packages/dashboard-ui/src/layouts/DashboardLayout.tsx`

2. **Domain Project Structure:**
   - `/root/projects/justSteve/src/domain/` (organization pattern)
   - `/root/projects/justSteve/src/api/index.ts` (integration)

3. **Documentation:**
   - `/root/packages/api-server/README.md`
   - `/root/projects/justSteve/ARCHITECTURE.md`

4. **Configuration:**
   - `/root/projects/justSteve/package.json` (dependencies)
   - `/root/projects/justSteve/tsconfig.json` (paths)

---

## Decision Log

### Why /root/packages/ and /root/projects/?

**Decision:** Two-tier structure separates infrastructure from domain code

**Rationale:**
- Clear dependency hierarchy (projects → packages)
- Packages are foundations, projects are applications
- Easy to understand: "Is this reusable infrastructure or domain logic?"

**Alternatives considered:**
- Monorepo with all in /root/projects/
  - ❌ Harder to see infrastructure vs. domain
- Separate repos for each package
  - ❌ Too much overhead for local development

---

### Why file:// protocol for development?

**Decision:** Use `file:` protocol during development, versions in production

**Rationale:**
- Instant reflection of changes (no publish cycle)
- Fast iteration on packages
- No npm registry required for development
- Easy to switch to versions later

**Alternatives considered:**
- npm link
  - ❌ Can cause issues with peer dependencies
  - ❌ Breaks when switching branches
- Publish to private registry
  - ❌ Slow iteration cycle
  - ❌ Requires registry infrastructure

---

### Why domain-driven organization?

**Decision:** Organize domain code by capability, not technical layer

**Rationale:**
- Business capabilities are more stable than technical patterns
- Easier to understand what code does
- Natural boundaries for testing
- Aligns with how developers think about features

**Alternatives considered:**
- MVC structure (models/views/controllers)
  - ❌ Scatters related code across folders
  - ❌ Harder to find all code for a feature
- Flat structure
  - ❌ Becomes messy with many files

---

### Why unopinionated infrastructure?

**Decision:** Shared packages provide tools, not rules

**Rationale:**
- Different projects have different needs
- Forces thoughtful design in each project
- Prevents "framework lock-in"
- Easier to maintain (less surface area)

**Alternatives considered:**
- Opinionated framework
  - ❌ Limits flexibility
  - ❌ Harder to customize
- No shared packages
  - ❌ Massive duplication

---

## Checklist for New Projects

Use this checklist when starting a new domain project:

### Setup
- [ ] Create project directory in `/root/projects/`
- [ ] Initialize package.json
- [ ] Add dependencies to `@myorg/api-server` and `@myorg/dashboard-ui`
- [ ] Create domain structure: `src/domain/{capability}/`
- [ ] Create API structure: `src/api/routes/`
- [ ] Create frontend structure: `src/frontend/components/`
- [ ] Set up tsconfig.json
- [ ] Install dependencies: `npm install --legacy-peer-deps`

### Implementation
- [ ] Identify domain capabilities (what does this project do?)
- [ ] Create folder for each capability in `src/domain/`
- [ ] Set up API server using `createApiServer()`
- [ ] Add domain-specific routes
- [ ] Set up frontend using `DashboardLayout` (or custom)
- [ ] Implement domain logic in capability folders
- [ ] Add tests for each capability

### Testing
- [ ] All tests passing
- [ ] Backend builds: `npm run build`
- [ ] Frontend builds: `npm run build:frontend`
- [ ] API health check works: `/api/health`
- [ ] No TypeScript errors
- [ ] No circular dependencies

### Documentation
- [ ] README.md explains what the project does
- [ ] README.md shows how to run it
- [ ] Document domain capabilities
- [ ] Add inline code comments
- [ ] Update this blueprint if you discover new patterns

---

## FAQ

**Q: Can I use these packages with JavaScript instead of TypeScript?**
A: Yes, but you lose type safety. The packages export compiled JavaScript in `dist/` which works with any project. However, TypeScript is strongly recommended for consistency.

**Q: What if I need a different framework (Vue, Angular)?**
A: You can still use `@myorg/api-server` for the backend. Create a separate UI package for your framework, or don't use the dashboard-ui package.

**Q: How do I publish these packages to npm?**
A:
```bash
cd /root/packages/api-server
npm publish --access public
```
Then update projects to use versions instead of `file://`.

**Q: Can I have multiple shared packages?**
A: Absolutely! Create packages for common needs:
- `@myorg/database-utils`
- `@myorg/auth-middleware`
- `@myorg/logging`

**Q: What if my project doesn't fit this pattern?**
A: That's fine! This pattern works for web applications with APIs and UIs. CLI-only tools, serverless functions, or experimental projects may need different approaches.

**Q: How do I handle breaking changes in shared packages?**
A: Use semantic versioning. Bump major version for breaking changes, update projects one at a time. The file:// protocol makes testing easy during development.

---

## Conclusion

This blueprint captures the pattern for building domain projects with shared infrastructure in our enterprise. It's based on real-world refactoring of the Wayback Archive Toolkit and designed to be applied to future sibling projects.

**Key takeaways:**
1. Infrastructure tier (`/root/packages/`) is reusable foundation
2. Domain tier (`/root/projects/`) is unique business value
3. Organize domain code by capability, not technical layer
4. Use file:// protocol for fast development iteration
5. Keep packages unopinionated and focused

**For future agents:**
- Use this document as your starting point
- Reference the Wayback Archive Toolkit as a working example
- Follow the 5-phase migration playbook
- Add new patterns you discover back to this blueprint

**Version history:**
- v1.0 (Oct 2025): Initial blueprint from Wayback Archive Toolkit refactoring

---

**Document maintained by:** Enterprise Architecture
**Last updated:** October 2025
**Next review:** When starting 3rd domain project
