# DataArchive

A file organization and cataloging system for WSL (Windows Subsystem for Linux). Scans drives, categorizes files by type and date, detects duplicates, identifies OS installations, and stores metadata in SQLite.

## QuickStart

**Prerequisites:** Python 3.6+, WSL (Ubuntu/Debian recommended)

```bash
# 1. Clone and install
git clone https://github.com/justSteve/DataArchive.git
cd DataArchive
chmod +x install.sh
./install.sh

# 2. Scan a drive
./dataarchive /mnt/e

# 3. View results in web UI
python3 archive_ui.py
# Navigate to http://localhost:5000
```

That's it. The tool scans your drive, prevents system sleep, and stores metadata in SQLite.

## Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                        4-Stage Pipeline                            │
├──────────────┬──────────────┬──────────────┬──────────────────────┤
│  Validation  │  Discovery   │ OS Detection │     File Scan        │
│              │              │              │                      │
│ drive_       │ drive_       │ os_          │ file_scanner.py      │
│ validator.py │ manager.py   │ detector.py  │                      │
└──────────────┴──────────────┴──────────────┴──────────────────────┘
         │              │              │                │
         └──────────────┴──────────────┴────────────────┘
                                │
                    ┌───────────┴───────────┐
                    │    SQLite Database    │
                    │    (archive.db)       │
                    └───────────┬───────────┘
                                │
              ┌─────────────────┼─────────────────┐
              │                 │                 │
      ┌───────┴───────┐ ┌───────┴───────┐ ┌───────┴───────┐
      │  CLI Output   │ │  Flask Web UI │ │  JSON Reports │
      │               │ │  :5000        │ │  reports/     │
      └───────────────┘ └───────────────┘ └───────────────┘
```

## Core Capabilities

| Feature | Description |
|---------|-------------|
| **Drive Validation** | Checks disk status, partitions, connectivity before scanning |
| **Hardware Discovery** | Detects model, serial, manufacturer via WSL PowerShell |
| **OS Detection** | Identifies Windows/Linux/macOS installations on drives |
| **File Scanning** | Recursive traversal with progress tracking |
| **File Categorization** | Organizes by type (images, videos, documents, etc.) |
| **Date Organization** | Groups files by year/month |
| **Duplicate Detection** | File hashing to identify duplicates |
| **Sleep Prevention** | Prevents Windows sleep during long scans (WSL-aware) |
| **Manual Drive Identity** | CLI flags for IDE/USB adapter scenarios |
| **Web UI** | Flask-based interface for viewing scan results |

## Usage

### Basic Scanning

```bash
# Scan a drive
./dataarchive /mnt/e

# Scan specific folder
./dataarchive /mnt/c/Users/steve/Documents

# Verbose output
./dataarchive /mnt/d --verbose
```

### Manual Drive Identification

For IDE drives or USB adapters that don't report drive identity:

```bash
./dataarchive /mnt/e \
  --drive-model "Western Digital WD800BB 80GB" \
  --drive-serial "WD-WMAM12345678" \
  --drive-notes "Blue case sticker, from old Dell desktop"
```

### Web UI

```bash
# Start the web interface
python3 archive_ui.py
# Navigate to http://localhost:5000
```

**Endpoints:**
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Main dashboard |
| `GET` | `/api/scans` | List all scan sessions |
| `GET` | `/api/files` | Query scanned files |
| `GET` | `/api/drives` | List cataloged drives |

## Command Reference

```bash
./dataarchive <path> [OPTIONS]

Options:
  --drive-model TEXT      Drive model (e.g., "Samsung 870 EVO 250GB")
  --drive-serial TEXT     Drive serial number
  --drive-notes TEXT      Additional notes about the drive
  --db PATH               Database file (default: output/archive.db)
  --no-progress           Disable progress bar
  --verbose               Enable verbose logging
```

## Database Schema

SQLite database at `output/archive.db`:

| Table | Purpose |
|-------|---------|
| `drives` | Cataloged drives with model, serial, notes |
| `scans` | Scan sessions with timestamps and statistics |
| `files` | File metadata (path, size, hash, timestamps) |
| `os_info` | Detected OS installations |
| `categories` | File type categories |

### Sample Queries

```sql
-- Find all files from a specific drive
SELECT f.filepath, f.size_bytes, f.file_hash
FROM files f
JOIN scans s ON f.scan_id = s.scan_id
JOIN drives d ON s.drive_id = d.drive_id
WHERE d.model LIKE '%Western Digital%';

-- Find drives with notes
SELECT model, serial_number, notes, first_seen
FROM drives
WHERE notes LIKE '%ThinkCentre%';
```

## Project Structure

```
DataArchive/
├── scan_drive.py           # Main entry point (4-stage pipeline)
├── archive_ui.py           # Flask web UI
├── dataarchive             # Launcher script (created by install.sh)
│
├── core/                   # Core domain logic
│   ├── file_scanner.py     # Recursive file traversal
│   ├── database.py         # SQLite operations
│   ├── drive_manager.py    # Hardware detection (WSL/PowerShell)
│   ├── drive_validator.py  # Pre-scan validation
│   ├── os_detector.py      # OS detection via filesystem
│   └── logger.py           # Logging configuration
│
├── utils/
│   └── power_manager.py    # WSL sleep prevention
│
├── packages/               # Infrastructure tier (TypeScript)
│   ├── api-server/         # Express server boilerplate
│   └── dashboard-ui/       # React + Material-UI components
│
├── templates/              # Flask HTML templates
├── output/                 # SQLite database (auto-created)
├── logs/                   # Application logs
│
├── install.sh              # Installation script
├── uninstall.sh            # Cleanup script
└── requirements.txt        # Python dependencies
```

## Configuration

### Python Dependencies

```
questionary    # Interactive CLI prompts
tqdm           # Progress bars
flask          # Web UI
flask-socketio # Real-time updates
```

### Infrastructure Packages (TypeScript)

For future expansion, shared packages are available:

| Package | Purpose |
|---------|---------|
| `@myorg/api-server` | Express server with CORS, health checks |
| `@myorg/dashboard-ui` | React + Material-UI dashboard components |

## Installation Details

The `install.sh` script:
1. Checks for Python and pip
2. Creates isolated virtual environment (`venv/`)
3. Installs all dependencies
4. Creates launcher script (`dataarchive`)

```bash
# Manual development setup
source venv/bin/activate
python3 scan_drive.py /path/to/test
deactivate
```

## Troubleshooting

### Permission denied
```bash
chmod +x install.sh uninstall.sh dataarchive
```

### Python not found
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv
```

### Cannot access Windows drives
Use the `/mnt/` prefix:
- C: drive = `/mnt/c`
- E: drive = `/mnt/e`

### System still goes to sleep
1. Check PowerShell accessibility: `powershell.exe -Command "Write-Host 'Test'"`
2. For very long scans, manually disable sleep in Windows settings

## Documentation

- [IDE Drives Guide](docs/IDE_DRIVES.md) - Working with USB-to-IDE adapters
- [Update Notes](docs/UPDATE_NOTES.md) - Sleep prevention & error handling
- [Structure Reference](docs/STRUCTURE.md) - Detailed component breakdown
- [Blueprint](docs/BLUEPRINT_README.md) - Enterprise architecture patterns
- [Refactoring Plan](docs/REFACTORING_PLAN.md) - Migration roadmap

## Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Core Logic | Python 3.6+ | Drive scanning, validation |
| CLI | Python + argparse | Command-line interface |
| Web UI | Flask + SocketIO | Results visualization |
| Database | SQLite | Metadata persistence |
| System | PowerShell (WSL) | Hardware detection, sleep prevention |
| Future UI | React + Material-UI | Modern dashboard |
| Future API | Express + TypeScript | REST endpoints |

## For .NET Developers

This Python application maps to familiar .NET concepts:

| Python | .NET Equivalent |
|--------|-----------------|
| `requirements.txt` | `packages.config` |
| `venv/` | `bin/` folder |
| `install.sh` | `Setup.exe` |
| `dataarchive` | Your `.exe` |
| Context manager (`with`) | `using` statement |
