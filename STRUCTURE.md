# DataArchive Repository Structure

## Overview

DataArchive is a Python-based file organization and cataloging tool designed for WSL (Windows Subsystem for Linux) environments. It scans external drives, organizes files by type and date, detects duplicates, captures OS information, and stores metadata in a SQLite database.

## Directory Layout

```
DataArchive/
├── Core Python Application
│   ├── scan_drive.py              # Main entry point, 4-stage pipeline
│   ├── archive_ui.py              # Flask web UI for results
│   │
│   ├── core/                      # Core domain logic
│   │   ├── file_scanner.py        # Recursive file traversal with progress
│   │   ├── database.py            # SQLite operations (drives, scans, files)
│   │   ├── drive_manager.py       # Hardware detection (WSL/PowerShell)
│   │   ├── drive_validator.py     # Pre-scan validation (connectivity, perms)
│   │   ├── os_detector.py         # OS detection via filesystem analysis
│   │   └── logger.py              # Logging configuration
│   │
│   └── utils/
│       └── power_manager.py       # WSL sleep prevention (context manager)
│
├── Configuration & Setup
│   ├── install.sh                 # Installation script (creates venv, deps)
│   ├── uninstall.sh               # Cleanup script
│   ├── requirements.txt           # Python deps: questionary, tqdm
│   └── dataarchive                # Launcher script (created by install.sh)
│
├── Documentation
│   ├── README.md                  # Main guide (usage, installation, structure)
│   ├── UPDATE_NOTES.md            # Sleep prevention & error handling improvements
│   ├── IDE_DRIVES.md              # Manual drive identification workflow
│   ├── BLUEPRINT_README.md        # Enterprise architecture reference
│   └── REFACTORING_PLAN.md        # Migration plan to enterprise architecture
│
├── Node.js/TypeScript Packages (Infrastructure Tier)
│   ├── packages/api-server/       # Express server boilerplate
│   │   └── src/
│   │       ├── server.ts
│   │       ├── middleware/
│   │       └── routes/
│   │
│   └── packages/dashboard-ui/     # React + Material-UI framework
│       └── src/
│           ├── components/
│           ├── layouts/
│           └── theme/
│
├── Projects (Domain Tier)
│   └── projects/justSteve/        # Domain-specific implementations
│
└── Runtime Directories (Auto-created)
    ├── logs/                      # Application logs
    ├── output/                    # Generated database (archive.db)
    ├── templates/                 # Flask templates
    └── venv/                      # Python virtual environment
```

## Key Components

### Core Application (Python)

| File | Lines | Purpose |
|------|-------|---------|
| `scan_drive.py` | 231 | Main entry point, orchestrates 4-stage pipeline |
| `core/database.py` | 278 | SQLite operations for drives, scans, files |
| `core/drive_manager.py` | 284 | Hardware detection via WSL/PowerShell |
| `core/drive_validator.py` | 240 | Pre-scan validation (connectivity, permissions) |
| `core/os_detector.py` | 212 | OS detection via filesystem analysis |
| `core/file_scanner.py` | 176 | Recursive file traversal with progress tracking |
| `utils/power_manager.py` | 187 | WSL sleep prevention during long scans |
| `archive_ui.py` | 177 | Flask web UI for viewing results |

### Infrastructure Packages (TypeScript/Node.js)

| Package | Purpose |
|---------|---------|
| `packages/api-server` | Express server with TypeScript, CORS, error handling |
| `packages/dashboard-ui` | React + Material-UI dashboard components |

## Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Core Logic | Python 3.6+ | Drive scanning, validation, detection |
| CLI Interface | Python + argparse | Command-line orchestration |
| Web UI | Flask + HTML | Results visualization |
| Database | SQLite | Metadata persistence |
| Infrastructure | TypeScript + Node.js | Express API, React dashboard |
| System Integration | PowerShell (WSL) | Hardware detection, sleep prevention |

## Core Capabilities

1. **Drive Validation** - Checks disk status, partitions, connectivity before scanning
2. **File Scanning** - Recursively traverses filesystem with progress tracking
3. **File Categorization** - Organizes by type (images, videos, documents, etc.)
4. **Date Organization** - Groups files by year/month
5. **Duplicate Detection** - Uses file hashing to identify duplicates
6. **OS Detection** - Analyzes filesystem to detect Windows/Linux/macOS installations
7. **Hardware Discovery** - Detects drive model, serial, manufacturer via WSL PowerShell
8. **Sleep Prevention** - Prevents Windows/system sleep during long scans
9. **Report Generation** - Creates human-readable summaries
10. **Metadata Storage** - Stores results in SQLite database + JSON

## Design Patterns

- **4-Stage Pipeline**: Validation → Discovery → OS Detection → File Scan
- **Context Manager Pattern**: Python's `with` statement for resource cleanup
- **WSL Integration**: Uses PowerShell to access Windows hardware APIs
- **Manual Drive Identity**: CLI flags for IDE/USB adapter scenarios

## Architectural Evolution

The project is transitioning from a Python-only stack to a polyglot architecture:

- **Current**: Python CLI + Flask UI
- **Future**: TypeScript/Node.js infrastructure tier with Python domain logic
  - Shared packages in `packages/`
  - Browser-based React UI
  - REST API via Express
