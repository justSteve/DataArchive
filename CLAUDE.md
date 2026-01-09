# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DataArchive v2 is a **Claude-assisted interactive drive inspection system** using a polyglot two-tier architecture:
- **Infrastructure Layer (TypeScript)**: Express API server + React UI
- **Domain Layer (Python)**: Multi-pass inspection, file scanning, hardware detection, OS detection
- **Integration**: TypeScript spawns Python processes via `child_process.spawn()` with JSON over stdout/stderr
- **Database**: Shared SQLite database (`output/archive.db`)

## Multi-Pass Inspection Workflow

| Pass | Purpose | Output |
|------|---------|--------|
| **1. Health** | chkdsk-level inspection, error handling | Health report |
| **2. OS Detection** | Windows boot/version via registry | Exact build/edition |
| **3. Metadata** | Full folder/file metadata capture | File catalog |
| **4. Review** | Claude-assisted decisions, duplicates | Decision report |

Reports are saved to `output/reports/` for Claude analysis.

## Essential Commands

### Development (Windows)

```bash
# Start both API and frontend
./start-dev.sh

# Or manually:
npm run api          # API server on port 3001
npm run dev          # Frontend dev server on port 5173

# Build
npm run build
npm run build:frontend
```

### Testing

```bash
npm test
npm test -- --watch
npm test -- --coverage
```

### Python Environment (Windows)

```bash
# Activate virtual environment
python\venv\Scripts\activate

# Install dependencies
cd python && pip install -r requirements.txt

# Run inspection (new v2 workflow)
python python/inspect_drive.py E:\ --session-id 1

# Legacy scan (v1 compatibility)
python python/scan_drive.py C:\ --db output/archive.db --json-output
```

## Directory Structure

```
DataArchive/
├── archive/v1-batch/          # Historical v1 documentation
├── docs/                      # Consolidated documentation
├── output/
│   ├── archive.db            # SQLite database
│   └── reports/              # Claude analysis reports
├── python/
│   ├── core/                 # Database, scanner, OS detector
│   ├── inspection/           # Multi-pass modules (pass1-4)
│   ├── reports/              # Report generation
│   └── utils/                # Helpers (hash, registry, chkdsk)
├── src/
│   ├── api/routes/           # Express routes (incl. inspections.ts)
│   ├── frontend/components/  # React UI (incl. InspectionWizard)
│   └── services/             # PythonBridge, DatabaseService
```

## Key Integration Points

### PythonBridge Service (`src/services/PythonBridge.ts`)

**Legacy Methods:**
- `scanDrive()` - Blocking full drive scan (v1)
- `scanDriveAsync()` - Non-blocking scan (v1)

**Inspection Methods (v2):**
- `startInspection(driveId, drivePath)` - Create inspection session
- `runPass(sessionId, passNumber)` - Execute specific pass
- `getPassReport(sessionId, passNumber)` - Retrieve pass results

### Database Schema

**Core Tables (v1 - preserved):**
- `drives`, `scans`, `files`, `os_info`, `scan_statistics`

**Inspection Tables (v2 - new):**
- `inspection_sessions` - Multi-pass session tracking
- `inspection_passes` - Per-pass results and reports
- `inspection_decisions` - User/Claude decisions
- `file_hashes` - Duplicate detection

### Report Generation

Reports for Claude analysis follow this format:
```markdown
# Drive Inspection Report: [Model] (S/N: [Serial])

## Summary
- Health: [status] | OS: [version] | Files: [count]

## Decision Points
### 1. [Decision Type]
[Description and options]

## Recommended Actions
[Numbered list]
```

## Platform Handling

- **Windows dev**: Direct Python/PowerShell execution
- **WSL inspection**: PowerShell via `powershell.exe`, filesystem via `/mnt/`
- **Detection**: Check `platform.uname().release` for "microsoft"

## Beads Integration

Use beads for inspection issue tracking:
```bash
bd create "Inspect: WD Elements 2TB" --type=task --priority=2
bd update <id> --status=in_progress
bd close <id> --reason="Completed"
```

## Troubleshooting

### Database not initialized
```bash
./quick-reset-db.sh
```

### Python venv not activated
```bash
cd python && venv\Scripts\activate && pip install -r requirements.txt
```

### Port already in use (Windows)
```powershell
netstat -ano | findstr :3001
taskkill /PID <pid> /F
```

## Important Constraints

### Process Communication
- **Always use JSON** for Python→TypeScript data exchange
- **Always use `--json-output`** flag when calling Python scripts
- **Never use shell strings** - use argument arrays to prevent injection

### SQLite Concurrency
- Python writes during inspections/scans
- TypeScript reads for API queries
- Only one inspection/scan should write at a time
