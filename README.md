# DataArchive - Drive Cataloging System

A polyglot architecture project combining TypeScript infrastructure with Python domain logic for cataloging and archiving drives.

## Overview

DataArchive scans drives and catalogs all files into a SQLite database, enabling you to browse and search files from drives that may not be currently connected. It features hardware detection, OS identification, and a modern web-based interface.

### Key Features

- **Drive Scanning**: Catalog entire drives with file metadata (size, dates, extensions)
- **Hardware Detection**: Automatic detection of drive model, serial number, and specifications
- **OS Detection**: Identify operating systems on scanned drives
- **Web Interface**: Modern React UI with real-time progress monitoring
- **File Browsing**: Paginated file browser with search and filter capabilities
- **Historical Tracking**: Track multiple scans of the same drive over time
- **Database Export**: SQLite database for easy querying and analysis

## Architecture

### Polyglot Design

DataArchive uses a two-tier polyglot architecture:

- **Infrastructure Layer** (TypeScript): Express API server + React UI with Vite
- **Domain Layer** (Python): Drive scanning, validation, OS detection, hardware queries
- **Integration**: TypeScript spawns Python processes and communicates via JSON over stdout/stderr

This design keeps infrastructure (API, UI) in TypeScript while preserving Python's strengths for system-level operations, file scanning, and hardware detection.

### Technology Stack

**Frontend:**
- React 18 with TypeScript
- Material-UI (MUI) components
- Vite for development and bundling
- Axios for API communication

**Backend:**
- Node.js with Express
- TypeScript for type safety
- Better-sqlite3 for database queries
- Child process spawning for Python integration

**Domain:**
- Python 3.6+
- SQLite database
- PowerShell integration (WSL/Windows)
- Questionary and tqdm libraries

### Directory Structure

```
data-archive/
├── src/
│   ├── domain/              # TypeScript domain models
│   │   └── models/
│   │       └── types.ts     # Interfaces matching Python data
│   │
│   ├── api/                 # Express API server
│   │   ├── routes/
│   │   │   ├── scans.ts     # Scan management endpoints
│   │   │   ├── drives.ts    # Drive validation endpoints
│   │   │   └── files.ts     # File browsing endpoints
│   │   └── index.ts         # Server entry point
│   │
│   ├── frontend/            # React UI
│   │   ├── components/
│   │   │   ├── DriveSelector.tsx    # Scan initiation
│   │   │   ├── ScanProgress.tsx     # Progress monitoring
│   │   │   ├── ScanDashboard.tsx    # Scan history
│   │   │   └── FileTree.tsx         # File browser
│   │   ├── App.tsx          # Main app with tabs
│   │   ├── main.tsx         # React entry point
│   │   └── index.html       # HTML template
│   │
│   └── services/            # Infrastructure services
│       ├── PythonBridge.ts  # Python process spawning
│       └── DatabaseService.ts # SQLite queries
│
├── python/                  # Python domain logic
│   ├── core/
│   │   ├── database.py      # Schema and DB operations
│   │   ├── drive_manager.py # Hardware detection
│   │   ├── drive_validator.py # Drive validation
│   │   ├── file_scanner.py  # File cataloging
│   │   ├── os_detector.py   # OS identification
│   │   └── logger.py        # Logging utilities
│   ├── utils/
│   │   └── power_manager.py # Sleep prevention
│   ├── scan_drive.py        # Main scan script
│   ├── requirements.txt     # Python dependencies
│   └── venv/                # Virtual environment
│
├── output/
│   └── archive.db           # SQLite database
│
├── dist/                    # Compiled TypeScript
├── package.json            # TypeScript dependencies
├── tsconfig.json           # TypeScript configuration
├── vite.config.ts          # Frontend bundling
└── start-dev.sh            # Development startup script
```

## Getting Started

### Prerequisites

- **Node.js 20+**
- **Python 3.6+**
- **Access to shared packages** at `/root/packages/`
  - `@myorg/api-server`
  - `@myorg/dashboard-ui`

### Installation

#### 1. Install TypeScript Dependencies

```bash
npm install --legacy-peer-deps
```

This installs Express, React, Material-UI, better-sqlite3, and links to shared packages.

#### 2. Install Python Dependencies

```bash
cd python
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cd ..
```

This creates a virtual environment and installs questionary and tqdm.

#### 3. Initialize Database

```bash
source python/venv/bin/activate
python3 -c "import sys; sys.path.insert(0, 'python'); from core.database import Database; Database('output/archive.db')"
```

This creates the SQLite database with all necessary tables.

#### 4. Build TypeScript

```bash
npm run build
```

Compiles TypeScript to JavaScript in the `dist/` directory.

### Running the Application

#### Option 1: Development Script (Recommended)

```bash
./start-dev.sh
```

Starts both API server and frontend dev server concurrently.

#### Option 2: Manual (Two Terminals)

**Terminal 1: API Server**
```bash
npm run api
```

**Terminal 2: Frontend Dev Server**
```bash
npm run dev
```

### Access the Application

- **Frontend**: http://localhost:5173
- **API**: http://localhost:3001
- **Health Check**: http://localhost:3001/api/health

## Usage

### Scanning a Drive

1. Open the application at http://localhost:5173
2. Navigate to the "New Scan" tab
3. Enter the drive path (e.g., `/mnt/c`, `/mnt/e`)
4. Click "Validate Drive" (optional) to check if the path is valid
5. Click "Start Scan"
6. The app automatically switches to the "Monitor" tab
7. Watch real-time progress as files are cataloged

### Browsing Files

1. Navigate to the "Browse Scans" tab
2. Click on a scan from the list
3. View files in the paginated table
4. Use the pagination controls to browse through files
5. Change rows per page (10, 25, 50, 100)

### Monitoring Active Scans

1. Navigate to the "Monitor" tab
2. See progress bar with file count
3. Status updates every 2 seconds
4. Completion status displayed automatically

## API Reference

### Health Check

```
GET /api/health
```

**Response:**
```json
{
  "status": "ok",
  "timestamp": "2025-10-20T15:21:26.525Z",
  "uptime": 454.108664042,
  "database": true
}
```

### Scans

#### List All Scans

```
GET /api/scans
```

**Response:**
```json
[
  {
    "scan_id": 1,
    "drive_id": 1,
    "scan_start": "2025-10-20T10:30:00.000Z",
    "scan_end": "2025-10-20T10:45:00.000Z",
    "mount_point": "/mnt/c",
    "file_count": 12345,
    "total_size_bytes": 1234567890,
    "status": "COMPLETE",
    "model": "Samsung 870 EVO 250GB",
    "serial_number": "S4BNN123456789"
  }
]
```

#### Get Scan Details

```
GET /api/scans/:id
```

#### Start New Scan

```
POST /api/scans/start
Content-Type: application/json

{
  "drivePath": "/mnt/c",
  "options": {
    "noProgress": true
  }
}
```

**Response:**
```json
{
  "success": true,
  "scan_id": 1,
  "file_count": 12345,
  "total_size": 1234567890,
  "status": "complete"
}
```

#### Get Scan Status

```
GET /api/scans/:id/status
```

**Response:**
```json
{
  "scanId": 1,
  "status": "COMPLETE",
  "filesProcessed": 12345,
  "progress": 100
}
```

### Drives

#### Validate Drive

```
POST /api/drives/validate
Content-Type: application/json

{
  "drivePath": "/mnt/c"
}
```

**Response:**
```json
{
  "valid": true,
  "errors": [],
  "warnings": []
}
```

#### Get Drive Info

```
POST /api/drives/info
Content-Type: application/json

{
  "drivePath": "/mnt/c"
}
```

### Files

#### Get Files for Scan

```
GET /api/files/:scanId?limit=25&offset=0
```

**Response:**
```json
{
  "files": [
    {
      "file_id": 1,
      "path": "/Users/username/Documents/file.txt",
      "size_bytes": 1024,
      "modified_date": "2025-01-15T10:30:00.000Z",
      "extension": ".txt",
      "is_hidden": false
    }
  ],
  "pagination": {
    "total": 12345,
    "limit": 25,
    "offset": 0
  }
}
```

## Database Schema

The SQLite database includes the following tables:

### drives
Physical drive information (serial number, model, size, connection type)

### scans
Scan sessions linked to drives (timestamps, file count, mount point)

### os_info
Operating system detection results (type, version, install date)

### files
Individual file records (path, size, dates, extension, flags)

### scan_statistics
Aggregated statistics per scan (extension counts, oldest/newest files)

See `python/core/database.py:40` for complete schema.

## Development

### Project Scripts

```bash
# Build TypeScript
npm run build

# Start API server (port 3001)
npm run api

# Start frontend dev server (port 5173)
npm run dev

# Start both servers concurrently
./start-dev.sh
```

### Python Scripts

```bash
# Activate virtual environment
source python/venv/bin/activate

# Run scan manually
python python/scan_drive.py /mnt/c

# Run with JSON output (for TypeScript integration)
python python/scan_drive.py /mnt/c --json-output

# Validate drive
python python/scan_drive.py /mnt/c --validate-only
```

### Adding New API Endpoints

1. Create route file in `src/api/routes/`
2. Import and register in `src/api/index.ts`
3. Add TypeScript types in `src/domain/models/types.ts`
4. Add Python functionality if needed
5. Update PythonBridge if calling Python

### Adding New React Components

1. Create component in `src/frontend/components/`
2. Import in `src/frontend/App.tsx`
3. Add to appropriate tab panel
4. Wire up state management callbacks

## Database Management

### Resetting the Database

To reset the database to a blank slate (with automatic backup):

**Option 1: Web UI (Recommended)**
- Navigate to the "Admin" tab
- Click "Reset Database"
- Confirm the action

**Option 2: Command Line (Interactive)**
```bash
./reset-database.sh
```
Shows database stats and asks for confirmation before resetting.

**Option 3: Quick Reset (No confirmation)**
```bash
./quick-reset-db.sh
```
Immediately resets database with automatic backup.

### Backups

All database resets automatically create a backup at:
```
output/backups/archive_backup_[timestamp].db
```

To restore a backup:
```bash
cp output/backups/archive_backup_20251020_160000.db output/archive.db
```

View backups in the Admin tab or list manually:
```bash
ls -lh output/backups/
```

## Troubleshooting

### Database Errors

**Issue**: `SqliteError: no such table: scans`

**Fix**: Initialize database schema:
```bash
source python/venv/bin/activate
python3 -c "from core.database import Database; Database('output/archive.db')"
```

Or use the reset script:
```bash
./quick-reset-db.sh
```

### Port Already in Use

**Issue**: `Error: listen EADDRINUSE: address already in use :::3001`

**Fix**: Kill existing process:
```bash
lsof -ti:3001 | xargs kill -9
```

### Python Virtual Environment Issues

**Issue**: `ModuleNotFoundError: No module named 'questionary'`

**Fix**: Reinstall Python dependencies:
```bash
cd python
source venv/bin/activate
pip install -r requirements.txt
```

### TypeScript Compilation Errors

**Issue**: Type errors or missing modules

**Fix**: Rebuild shared packages first:
```bash
cd /root/packages/api-server && npm run build
cd /root/packages/dashboard-ui && npm run build
cd /root/projects/data-archive && npm run build
```

### Frontend Not Loading

**Issue**: Blank page or React errors

**Fix**: Check browser console for errors. Ensure API server is running:
```bash
curl http://localhost:3001/api/health
```

## Project Status

✅ **Phase 1 Complete**: TypeScript infrastructure bootstrapped
✅ **Phase 2 Complete**: Python code moved and bridge implemented
✅ **Phase 3 Complete**: React frontend with 4 major components
✅ **Phase 4 Complete**: Testing and integration verified
🔄 **Phase 5 In Progress**: Documentation and polish

**Overall Progress**: 80% (4/5 phases complete)

## Shared Packages

This project uses the enterprise architecture pattern from Steve's Sites:

- **@myorg/api-server** - Express boilerplate with CORS, health checks, error handling
- **@myorg/dashboard-ui** - React components, Material-UI theme, and layout

Packages are linked via `file://` protocol in package.json for fast local development.

## Documentation

- [REFACTORING_PLAN.md](REFACTORING_PLAN.md) - Complete 5-phase migration strategy
- [PHASE1_COMPLETE.md](PHASE1_COMPLETE.md) - TypeScript infrastructure setup
- [PHASE2_COMPLETE.md](PHASE2_COMPLETE.md) - Python integration details
- [PHASE3_COMPLETE.md](PHASE3_COMPLETE.md) - React component documentation
- [PHASE4_COMPLETE.md](PHASE4_COMPLETE.md) - Testing and verification results
- [ARCHITECTURE.md](../DataArchive/ARCHITECTURE.md) - Original Python architecture
- [CLAUDE.md](../DataArchive/CLAUDE.md) - Claude Code guidance

## Contributing

When contributing to this project:

1. Follow the polyglot architecture pattern
2. Keep infrastructure in TypeScript, domain logic in Python
3. Communicate between layers via JSON
4. Add tests for new functionality
5. Update relevant documentation

## License

MIT

## Contact

For questions or issues, refer to the documentation files or check the GitHub repository.
