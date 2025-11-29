# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DataArchive is a drive cataloging system using a **polyglot two-tier architecture**:
- **Infrastructure Layer (TypeScript)**: Express API server + React UI
- **Domain Layer (Python)**: File scanning, hardware detection, OS detection
- **Integration**: TypeScript spawns Python processes via `child_process.spawn()` and communicates via JSON over stdout/stderr
- **Database**: Shared SQLite database (`output/archive.db`)

## Essential Commands

### Development Workflow

```bash
# Start development environment (recommended - runs both API and frontend)
./start-dev.sh

# OR manually in separate terminals:
npm run api          # API server on port 3001
npm run dev          # Frontend dev server on port 5173

# Build TypeScript
npm run build

# Build frontend for production
npm run build:frontend
```

### Testing

```bash
# Run tests
npm test

# Watch mode
npm test:watch

# Coverage report
npm test:coverage
```

### Python Environment

```bash
# Activate Python virtual environment (required before manual Python operations)
source python/venv/bin/activate

# Install/update Python dependencies
cd python && pip install -r requirements.txt

# Initialize database (creates schema)
python3 -c "import sys; sys.path.insert(0, 'python'); from core.database import Database; Database('output/archive.db')"

# Run manual scan
python python/scan_drive.py /mnt/c --db output/archive.db --json-output
```

### Initial Setup

```bash
# 1. Install Node dependencies (use --legacy-peer-deps for React compatibility)
npm install --legacy-peer-deps

# 2. Setup Python virtual environment
cd python
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cd ..

# 3. Initialize database
source python/venv/bin/activate
python3 -c "import sys; sys.path.insert(0, 'python'); from core.database import Database; Database('output/archive.db')"

# 4. Build TypeScript
npm run build
```

## Architecture Deep Dive

### Critical Design Pattern: Process Spawning

The core integration mechanism uses **subprocess spawning** rather than microservices or HTTP APIs:

```typescript
// TypeScript spawns Python processes
const python = spawn('python/venv/bin/python3', [
  'python/scan_drive.py',
  drivePath,
  '--db', dbPath,
  '--json-output'
]);
```

**Why this matters:**
- Python writes to database during scans
- TypeScript reads from database for API responses
- No REST API between layers - direct subprocess communication
- Arguments passed as arrays to prevent command injection
- JSON output captured from stdout

### Directory Structure

```
data-archive/
├── src/
│   ├── api/                    # Express server and routes
│   │   ├── routes/
│   │   │   ├── scans.ts        # POST /api/scans/start, GET /api/scans
│   │   │   ├── drives.ts       # POST /api/drives/validate
│   │   │   └── files.ts        # GET /api/files/:scanId
│   │   └── index.ts            # Server entry point
│   │
│   ├── services/
│   │   ├── PythonBridge.ts     # CRITICAL: Python subprocess spawning
│   │   └── DatabaseService.ts  # SQLite queries from TypeScript
│   │
│   ├── frontend/               # React UI (Vite)
│   │   ├── components/
│   │   │   ├── DriveSelector.tsx
│   │   │   ├── ScanProgress.tsx
│   │   │   ├── ScanDashboard.tsx
│   │   │   └── FileTree.tsx
│   │   ├── App.tsx
│   │   └── main.tsx
│   │
│   └── domain/models/types.ts  # TypeScript interfaces matching Python data
│
├── python/
│   ├── core/
│   │   ├── database.py         # SQLite schema and operations
│   │   ├── drive_manager.py    # Hardware detection (PowerShell)
│   │   ├── drive_validator.py  # Path validation
│   │   ├── file_scanner.py     # Recursive file cataloging
│   │   ├── os_detector.py      # OS identification
│   │   └── logger.py           # Python logging
│   │
│   ├── scan_drive.py           # Main entry point (called by PythonBridge)
│   ├── requirements.txt        # questionary, tqdm
│   └── venv/                   # Virtual environment
│
└── output/
    └── archive.db              # SQLite database (shared)
```

### Key Integration Points

#### 1. PythonBridge Service (`src/services/PythonBridge.ts`)

**Purpose**: Spawn Python scripts and parse JSON responses

**Methods to know:**
- `scanDrive(drivePath, dbPath, options)` - Start full drive scan
- `validateDrive(drivePath)` - Check if path is valid
- `getDriveInfo(drivePath)` - Get hardware specs via PowerShell

**Always:**
- Pass arguments as array (not shell string) to prevent injection
- Use `--json-output` flag for Python scripts
- Parse stdout as JSON, stderr as errors

#### 2. Python scan_drive.py Entry Point

**Arguments:**
```bash
python scan_drive.py <drive_path> \
  --db <db_path> \
  --json-output \
  --no-progress \
  [--drive-model MODEL] \
  [--drive-serial SERIAL] \
  [--validate-only]
```

**Output format (stdout):**
```json
{
  "success": true,
  "scan_id": 1,
  "file_count": 12345,
  "total_size": 1234567890,
  "status": "complete"
}
```

#### 3. Database Schema (`python/core/database.py`)

**Tables:**
- `drives` - Physical drive info (serial, model, size)
- `scans` - Scan sessions (timestamps, file count, mount point)
- `files` - Individual file records (path, size, extension, dates)
- `os_info` - Operating system detection results
- `scan_statistics` - Aggregated stats per scan

**Important indexes:**
- `idx_files_scan_path` - For file queries by scan_id
- `idx_files_extension` - For file type analysis

### Shared Packages

This project depends on monorepo packages at `/root/packages/`:

- **@myorg/api-server** - Express boilerplate (CORS, health checks, error handling)
- **@myorg/dashboard-ui** - React components, MUI theme, layout

**When shared packages change:**
```bash
# Rebuild shared packages first
cd /root/packages/api-server && npm run build
cd /root/packages/dashboard-ui && npm run build

# Then rebuild this project
cd /root/projects/data-archive && npm run build
```

**Important:** Use `npm install --legacy-peer-deps` due to React version constraints.

## Common Development Tasks

### Adding a New API Endpoint

1. Create/modify route in `src/api/routes/`
2. Register route in `src/api/index.ts`
3. Add TypeScript types in `src/domain/models/types.ts`
4. If calling Python: Update `PythonBridge.ts` with new method
5. Test with `curl http://localhost:3001/api/your-endpoint`

### Adding a Python Function

1. Add function to appropriate module in `python/core/`
2. If called from TypeScript: Add CLI args to `python/scan_drive.py`
3. Update PythonBridge to pass new arguments
4. Ensure JSON output format for subprocess communication

### Adding a React Component

1. Create component in `src/frontend/components/`
2. Import in `src/frontend/App.tsx`
3. Wire up with state callbacks (`onScanStarted`, `onScanSelected`)
4. Use Material-UI components for consistency with shared package

### Modifying Database Schema

1. Edit `python/core/database.py` `_init_schema()` method
2. Drop existing database: `rm output/archive.db`
3. Reinitialize: `python3 -c "from core.database import Database; Database('output/archive.db')"`
4. Update TypeScript interfaces in `src/domain/models/types.ts`

## React Deduplication Critical Fix

**Problem**: Multiple React instances cause hooks errors with shared packages.

**Solution applied** (already in `vite.config.ts`):
```typescript
resolve: {
  alias: {
    'react': path.resolve(__dirname, './node_modules/react'),
    'react-dom': path.resolve(__dirname, './node_modules/react-dom'),
    'react/jsx-runtime': path.resolve(__dirname, './node_modules/react/jsx-runtime')
  },
  dedupe: ['react', 'react-dom']
}
```

**If hooks errors occur:**
1. Verify Vite config has resolve aliases
2. Check `npm ls react` shows single version tree
3. Rebuild with `npm run build`

## Database Management

### Resetting the Database

Three ways to reset database to blank slate (all create automatic backups):

1. **Web UI**: Admin tab → Reset Database button
2. **Interactive**: `./reset-database.sh` (asks for confirmation)
3. **Quick**: `./quick-reset-db.sh` (no confirmation)

Backups saved to: `output/backups/archive_backup_[timestamp].db`

### Important Database Operations

```bash
# Initialize fresh database
source python/venv/bin/activate
python3 -c "from core.database import Database; Database('output/archive.db')"

# Or use quick reset
./quick-reset-db.sh

# View database stats
sqlite3 output/archive.db "SELECT COUNT(*) FROM scans"

# Restore backup
cp output/backups/archive_backup_20251020_160000.db output/archive.db
```

## Troubleshooting

### "SqliteError: no such table: scans"
Database not initialized. Run:
```bash
./quick-reset-db.sh
```

### "ModuleNotFoundError: No module named 'questionary'"
Python venv not activated or dependencies not installed:
```bash
cd python
source venv/bin/activate
pip install -r requirements.txt
```

### Port 3001 or 5173 already in use
Kill existing processes:
```bash
lsof -ti:3001 | xargs kill -9
lsof -ti:5173 | xargs kill -9
```

### TypeScript compilation errors
Rebuild shared packages first:
```bash
cd /root/packages/api-server && npm run build
cd /root/packages/dashboard-ui && npm run build
cd /root/projects/data-archive && npm run build
```

### Frontend blank page
1. Check browser console for errors
2. Verify API is running: `curl http://localhost:3001/api/health`
3. Check Vite proxy configuration in `vite.config.ts`

### Python subprocess fails
1. Check Python path: `ls python/venv/bin/python3`
2. Test script manually: `source python/venv/bin/activate && python python/scan_drive.py /mnt/c --json-output`
3. Review stderr output in PythonBridge error messages

## Important Constraints

### WSL/PowerShell Dependency
- Hardware detection uses `powershell.exe` via WSL
- Requires Windows host with PowerShell access
- Won't work on pure Linux (will fallback gracefully)

### SQLite Concurrency
- Python writes during scans
- TypeScript reads for API queries
- SQLite handles read concurrency safely
- Only one scan should write at a time

### Process Communication
- **Always use JSON** for Python→TypeScript data exchange
- **Always use `--json-output`** flag when calling Python scripts
- **Never use shell strings** - use argument arrays to prevent injection

## Testing Notes

### Integration Test
The `test-integration.js` file tests the full polyglot stack:
- Spawns Python scan process
- Verifies JSON output
- Checks database was populated
- Confirms TypeScript can query results

Run before committing significant changes.

## Project Status

- ✅ Phase 1-5 Complete (infrastructure, Python integration, React UI, testing, docs)
- Database schema: Stable
- API routes: Complete
- Frontend: 4 major components (DriveSelector, ScanProgress, ScanDashboard, FileTree)
- Python modules: 6 core modules functional

See `PHASE*_COMPLETE.md` files for detailed implementation history.
