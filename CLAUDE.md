# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DataArchive is a file cataloging and archival system designed for WSL (Windows Subsystem for Linux) environments. It scans drives, catalogs file metadata, detects operating systems, and provides a web UI for browsing and selecting files for archival.

The project is designed for users who need to catalog and archive multiple external drives with proper hardware identification tracking (not dock/adapter identity, but the actual physical drive).

## Technology Stack

- **Language**: Python 3.6+
- **Database**: SQLite
- **Web Framework**: Flask + SocketIO (for UI)
- **Progress Display**: tqdm
- **Interactive Prompts**: questionary
- **Environment**: Python virtual environment (venv)

## Common Commands

### Installation & Setup

```bash
# Install system dependencies (if needed)
sudo apt update
sudo apt install python3 python3-pip python3-venv

# Run the automated installer
chmod +x install.sh
./install.sh
```

The installer creates a virtual environment, installs dependencies, and creates a launcher script.

### Running the Application

```bash
# Scan a drive using the launcher
./dataarchive /mnt/e

# Scan with custom database location
./dataarchive /mnt/e --db output/custom.db

# Scan without progress bar
./dataarchive /mnt/e --no-progress

# Manually specify drive identity (when auto-detection fails)
./dataarchive /mnt/e --drive-model "Samsung 870 EVO 250GB" --drive-serial "S123456" --drive-notes "Blue label"

# Launch web UI to browse scan results
python archive_ui.py
# Then navigate to http://localhost:5000
```

### Development

```bash
# Activate virtual environment for development
source venv/bin/activate

# Run scanner directly (without launcher)
python3 scan_drive.py /path/to/drive

# Run UI directly
python3 archive_ui.py

# Deactivate when done
deactivate

# Query database directly
sqlite3 output/archive.db
# Example queries:
# SELECT * FROM drives;
# SELECT * FROM scans ORDER BY scan_start DESC LIMIT 5;
# SELECT COUNT(*) FROM files WHERE scan_id = 1;
```

## Architecture

### Core Design Pattern: 4-Stage Scan Pipeline

The application uses a staged pipeline architecture for scanning drives:

1. **Stage 0: Drive Validation** - Pre-flight checks (connectivity, health, disk status)
2. **Stage 1: Drive Discovery** - Hardware identification (model, serial, filesystem)
3. **Stage 2: OS Detection** - Operating system detection via filesystem signatures
4. **Stage 3: File Scan** - Full recursive file catalog with batched database inserts
5. **Stage 4: Statistics** - Post-scan analysis and reporting

Each stage is independent and logs its progress, making it easy to debug issues at specific points.

### Module Organization

```
DataArchive/
├── scan_drive.py           # Main entry point - orchestrates the 4-stage pipeline
├── archive_ui.py           # Flask web UI for browsing scans and selecting files
├── core/                   # Core scanning and data management
│   ├── file_scanner.py     # File system traversal and metadata extraction
│   ├── database.py         # SQLite schema and queries
│   ├── drive_manager.py    # Physical drive identification (WSL PowerShell bridge)
│   ├── drive_validator.py  # Pre-scan validation (health checks, connectivity)
│   ├── os_detector.py      # OS detection via filesystem signatures
│   └── logger.py           # Centralized logging (console + file)
├── utils/
│   └── power_manager.py    # WSL-aware sleep prevention (context manager)
├── templates/              # Flask HTML templates for web UI
├── output/                 # Default location for archive.db
└── logs/                   # Application logs (timestamped)
```

### Key Architectural Decisions

**Physical Drive Identity**: The system uses PowerShell queries from WSL to get actual drive hardware identity (serial number, model) rather than USB adapter/dock identity. This ensures proper tracking when drives are connected via different adapters.

**Batched Inserts**: Files are inserted into the database in batches of 1000 to optimize performance during large scans.

**Context Manager for Sleep Prevention**: Uses Python's `with` statement to prevent system sleep during scans, automatically restored on exit or interruption.

**Database Schema**: The schema separates physical drives (`drives` table) from scan sessions (`scans` table), allowing multiple scans of the same drive over time. Files are linked to scan sessions, not directly to drives.

### Database Schema

The SQLite database has 5 main tables:

- **drives**: Physical drive records (serial number, model, size, connection type)
- **scans**: Scan sessions (linked to drives, records start/end time, file count)
- **files**: File metadata (path, size, dates, extension) - linked to scans
- **os_info**: OS detection results per scan
- **scan_statistics**: Aggregate statistics per scan

Primary relationships:
- `drives` 1:N `scans` (one drive, many scan sessions)
- `scans` 1:N `files` (one scan, many files)
- `scans` 1:1 `os_info` (one scan, one OS detection result)

### WSL-Specific Implementation Details

**Drive Access**: Windows drives are accessed via `/mnt/c`, `/mnt/e`, etc.

**Hardware Queries**: Physical drive identity is queried using PowerShell via WSL interop:
- `Get-PhysicalDisk` for drive serial number, model, media type
- `Get-Partition` to map drive letters to disk numbers
- Located at: `/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe`

**Sleep Prevention**: Uses PowerShell's `powercfg` command to prevent Windows system sleep during scans.

### Web UI Architecture

The web UI (archive_ui.py) is a Flask + SocketIO application that:
- Lists completed scans from the database
- Displays file trees for each scan (up to 3 levels deep)
- Provides a jsTree-based UI for selecting/excluding paths
- Planned: Initiate actual file copy operations (not yet implemented)

## Development Workflow

### Adding New File Type Detection

1. File extensions are already extracted in `file_scanner.py` (line 114)
2. To add categorization, query the `files` table by extension in your analysis
3. Consider adding a `file_type` column to the schema for classification

### Adding New Drive Platforms

The `DriveManager` class has platform-specific detection methods:
- `_detect_wsl_drives()` - Currently implemented
- `_detect_linux_drives()` - Stub for bare metal Linux
- `_detect_windows_drives()` - Stub for native Windows

Implement the appropriate method for your platform.

### Testing Drive Validation

The `DriveValidator` class (core/drive_validator.py) performs pre-scan checks. To test validation logic, create a validator instance and call `validate()`:

```python
from core.drive_validator import DriveValidator
validator = DriveValidator('/mnt/e')
results = validator.validate()
validator.print_validation_report(results)
```

## Known Limitations

- Hardware identification currently only works in WSL (requires PowerShell)
- Web UI archival action is not yet implemented (placeholder only)
- Bare metal Linux and native Windows drive detection are stubs
- No duplicate file detection yet (hashing would be needed)
- Progress bar file counting can be slow on very large drives

## Future Directions

The project author has noted plans to:
- Apply the enterprise architecture blueprint pattern (see BLUEPRINT_README.md)
- Extract shared infrastructure into packages (@myorg/api-server, @myorg/dashboard-ui)
- Potentially build a Discord archival tool as a separate domain project
- Extend the processor architecture for new file types or data processing (mentioned in README.md)
