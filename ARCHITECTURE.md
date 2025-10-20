# DataArchive Architecture

## Overview

DataArchive uses a **polyglot two-tier architecture** that combines TypeScript for infrastructure and Python for domain logic. This document explains the architectural decisions, component interactions, and design patterns used throughout the system.

## Architecture Pattern

### Two-Tier Polyglot Design

```
┌─────────────────────────────────────────────────────┐
│           Infrastructure Tier (TypeScript)          │
│  ┌────────────┐              ┌─────────────────┐   │
│  │  React UI  │◄────HTTP────►│  Express API    │   │
│  │  (Vite)    │              │  (Node.js)      │   │
│  └────────────┘              └─────────┬───────┘   │
│                                        │            │
│                              ┌─────────▼───────┐   │
│                              │  PythonBridge   │   │
│                              │  (child_process)│   │
│                              └─────────┬───────┘   │
└──────────────────────────────────────┼─────────────┘
                                       │ JSON
                                       │ stdin/stdout
┌──────────────────────────────────────▼─────────────┐
│             Domain Tier (Python)                    │
│  ┌──────────────┐  ┌──────────────┐                │
│  │ File Scanner │  │Drive Manager │                │
│  └──────┬───────┘  └──────┬───────┘                │
│         │                 │                         │
│         └────────┬────────┘                         │
│                  │                                  │
│         ┌────────▼────────┐                         │
│         │    Database     │                         │
│         │    (SQLite)     │                         │
│         └─────────────────┘                         │
└─────────────────────────────────────────────────────┘
```

### Why Polyglot?

**TypeScript Strengths:**
- Modern web development tooling (React, Vite, Express)
- Strong type system for API contracts
- Rich ecosystem for HTTP servers and UI frameworks
- Easy integration with shared packages (@myorg/*)

**Python Strengths:**
- System-level operations (file scanning, hardware detection)
- PowerShell integration for WSL/Windows
- Simple subprocess model for OS commands
- Mature libraries for file operations

**The Integration:**
- TypeScript handles HTTP requests, UI rendering, and routing
- Python handles file system operations, drive detection, and scanning
- Communication via JSON over stdin/stdout (subprocess spawning)
- Shared SQLite database for persistence

## Component Architecture

### Infrastructure Layer (TypeScript)

#### 1. Express API Server

**Location**: `src/api/index.ts`

**Responsibilities:**
- HTTP request handling
- Route registration
- Error handling middleware
- CORS configuration
- Database connection management

**Key Dependencies:**
- `@myorg/api-server` - Shared infrastructure package
- `express` - HTTP server framework
- `better-sqlite3` - Synchronous SQLite queries

**Example:**
```typescript
import { createApiServer, startServer } from '@myorg/api-server';

const app = createApiServer({
  dbPath: './output/archive.db',
  enableLogging: true
});

app.use('/api/scans', scansRouter);
app.use('/api/drives', drivesRouter);
app.use('/api/files', filesRouter);

startServer(app, 3001);
```

#### 2. API Routes

**Location**: `src/api/routes/`

**scans.ts** - Scan management
- `GET /api/scans` - List all scans
- `GET /api/scans/:id` - Get scan details
- `POST /api/scans/start` - Start new scan (calls PythonBridge)
- `GET /api/scans/:id/status` - Get scan progress

**drives.ts** - Drive operations
- `POST /api/drives/validate` - Validate drive path (calls PythonBridge)
- `POST /api/drives/info` - Get hardware info (calls PythonBridge)

**files.ts** - File browsing
- `GET /api/files/:scanId` - Get files with pagination
- Query parameters: `limit`, `offset`

#### 3. PythonBridge Service

**Location**: `src/services/PythonBridge.ts`

**Purpose**: Spawn Python processes and handle JSON communication

**Key Methods:**

```typescript
class PythonBridge {
  // Validate a drive path
  async validateDrive(drivePath: string): Promise<ValidationResult>

  // Scan a drive and catalog files
  async scanDrive(
    drivePath: string,
    dbPath: string,
    options: ScanOptions
  ): Promise<ScanResult>

  // Get hardware information
  async getDriveInfo(drivePath: string): Promise<DriveInfo>

  // Generic Python script executor
  private executePython<T>(
    scriptPath: string,
    args: string[]
  ): Promise<T>
}
```

**How it works:**

1. Construct arguments array
2. Spawn Python process using `child_process.spawn()`
3. Use venv Python: `python/venv/bin/python3`
4. Capture stdout and parse JSON
5. Capture stderr for errors
6. Return typed TypeScript result

**Example call:**
```typescript
const result = await bridge.scanDrive('/mnt/c', 'output/archive.db', {
  noProgress: true
});
// Returns: { scan_id, file_count, total_size, status }
```

#### 4. DatabaseService

**Location**: `src/services/DatabaseService.ts`

**Purpose**: Query SQLite database from TypeScript

**Key Methods:**

```typescript
class DatabaseService {
  // Get all scans
  getScans(limit: number = 100): ScanInfo[]

  // Get single scan by ID
  getScan(scanId: number): ScanInfo | undefined

  // Get files for a scan with pagination
  getFiles(
    scanId: number,
    limit: number,
    offset: number
  ): { files: FileInfo[], total: number }
}
```

**Why both TypeScript and Python access the database?**
- **Python writes**: During scans, Python inserts drive info, scans, and files
- **TypeScript reads**: API queries database to serve UI requests
- **Synchronization**: SQLite handles concurrent access safely

#### 5. React Frontend

**Location**: `src/frontend/`

**Component Hierarchy:**

```
App.tsx (DashboardLayout)
└── Tabs
    ├── Tab 1: New Scan
    │   ├── DriveSelector
    │   └── ScanDashboard
    ├── Tab 2: Monitor
    │   ├── ScanProgress (if active scan)
    │   └── ScanDashboard
    └── Tab 3: Browse
        ├── ScanDashboard
        └── FileTree
```

**State Management:**
- `tabValue` - Current active tab (0, 1, 2)
- `activeScanId` - Currently running scan
- `selectedScanId` - Scan selected for browsing
- `refreshTrigger` - Counter to force re-fetch

**Data Flow:**

```
User clicks "Start Scan"
  ↓
DriveSelector calls POST /api/scans/start
  ↓
onScanStarted(scanId) callback
  ↓
App sets activeScanId, switches to tab 1
  ↓
ScanProgress polls GET /api/scans/:id/status every 2s
  ↓
On complete: onComplete() callback
  ↓
App clears activeScanId, increments refreshTrigger
  ↓
ScanDashboard re-fetches scan list
```

**Key Components:**

**DriveSelector** - Scan initiation
- Input: Drive path
- Actions: Validate, Start Scan
- Options: Disable progress bar
- Callback: `onScanStarted(scanId)`

**ScanProgress** - Real-time monitoring
- Props: `scanId`, `onComplete`
- Polling interval: 2000ms
- Progress bar, file count, status chip
- Auto-cleanup on unmount

**ScanDashboard** - Scan history list
- Props: `onScanSelected`, `refreshTrigger`
- Displays: Model, serial, files, size, date
- Click to browse: Calls `onScanSelected(scanId)`

**FileTree** - File browser
- Props: `scanId`
- Pagination: 10/25/50/100 rows per page
- Table columns: Path, Size, Extension, Modified
- Icons: File type, hidden indicator

### Domain Layer (Python)

#### 1. Database Module

**Location**: `python/core/database.py`

**Purpose**: SQLite schema definition and data persistence

**Key Classes:**

```python
class Database:
    def __init__(self, db_path: str = "output/archive.db")
    def _init_schema(self)  # Create tables and indexes
    def insert_drive(self, drive_info: Dict) -> int
    def start_scan(self, drive_id: int, mount_point: str) -> int
    def complete_scan(self, scan_id: int, file_count: int, total_size: int)
    def insert_files_batch(self, scan_id: int, files: List[Dict])
    def insert_os_info(self, scan_id: int, os_info: Dict)
```

**Schema Tables:**
- `drives` - Physical drive metadata
- `scans` - Scan sessions
- `files` - Individual file records
- `os_info` - OS detection results
- `scan_statistics` - Aggregated stats

#### 2. Drive Manager

**Location**: `python/core/drive_manager.py`

**Purpose**: Hardware detection via PowerShell (WSL)

**Key Functions:**
```python
def get_drive_info(mount_point: str) -> Dict
    # Queries: Model, SerialNumber, Size, MediaType, BusType
    # Uses: powershell.exe -Command "Get-PhysicalDisk | ..."
```

#### 3. Drive Validator

**Location**: `python/core/drive_validator.py`

**Purpose**: Validate drive path before scanning

**Checks:**
- Path exists
- Path is directory
- Path is readable
- Drive is mounted
- Sufficient permissions

#### 4. File Scanner

**Location**: `python/core/file_scanner.py`

**Purpose**: Recursively scan directory and catalog files

**Key Functions:**
```python
def scan_files(
    root_path: str,
    scan_id: int,
    db: Database,
    show_progress: bool = True
) -> Tuple[int, int]:
    # Returns: (file_count, total_size)
```

**Features:**
- Recursive directory traversal
- Progress bar with tqdm
- Batch inserts (100 files at a time)
- Hidden file detection
- Extension extraction
- Error handling for permission denied

#### 5. OS Detector

**Location**: `python/core/os_detector.py`

**Purpose**: Detect operating system on scanned drive

**Detection Methods:**
- Windows: Check for `Windows/System32`, registry files
- Linux: Check for `/etc/`, `/boot/`
- macOS: Check for `/System/Library/`

**Information Extracted:**
- OS type, name, version
- Build number
- Edition
- Install date
- Boot capability

#### 6. Main Scan Script

**Location**: `python/scan_drive.py`

**Purpose**: CLI entry point with JSON output support

**Command Line Arguments:**
```bash
python scan_drive.py /mnt/c \
  --db output/archive.db \
  --no-progress \
  --json-output \
  --drive-model "Samsung 870 EVO" \
  --validate-only
```

**JSON Output Format:**
```json
{
  "success": true,
  "scan_id": 1,
  "file_count": 12345,
  "total_size": 1234567890,
  "status": "complete",
  "drive_info": {
    "model": "Samsung 870 EVO 250GB",
    "serial_number": "S4BNN123456789"
  }
}
```

**Error Format:**
```json
{
  "success": false,
  "error": "Drive not found",
  "details": "Path /mnt/z does not exist"
}
```

## Data Flow Diagrams

### Scan Workflow

```
User clicks "Start Scan" (/mnt/c)
         │
         ▼
POST /api/scans/start { drivePath: "/mnt/c" }
         │
         ▼
scans.ts route handler
         │
         ├──► Validate drive via PythonBridge
         │         │
         │         ▼
         │    Spawn: python validate_drive.py /mnt/c
         │         │
         │         ▼
         │    Return: { valid: true, errors: [] }
         │
         ├──► Start scan via PythonBridge
         │         │
         │         ▼
         │    Spawn: python scan_drive.py /mnt/c --json-output
         │         │
         │         ▼
         │    Python:
         │      1. Get drive hardware info (PowerShell)
         │      2. Insert/update drive in DB
         │      3. Create scan record
         │      4. Scan files recursively
         │      5. Insert files in batches
         │      6. Detect OS
         │      7. Complete scan
         │         │
         │         ▼
         │    Return: { scan_id: 1, file_count: 12345 }
         │
         ▼
Return scan_id to frontend
         │
         ▼
Frontend switches to Monitor tab
         │
         ▼
ScanProgress polls /api/scans/1/status every 2s
         │
         ▼
scans.ts queries DatabaseService.getScan(1)
         │
         ▼
Return: { status: "COMPLETE", filesProcessed: 12345 }
```

### File Browse Workflow

```
User clicks scan in ScanDashboard
         │
         ▼
onScanSelected(scanId = 1) callback
         │
         ▼
App switches to Browse tab
         │
         ▼
FileTree component receives scanId=1
         │
         ▼
GET /api/files/1?limit=25&offset=0
         │
         ▼
files.ts route handler
         │
         ▼
DatabaseService.getFiles(1, 25, 0)
         │
         ▼
SQL: SELECT * FROM files WHERE scan_id=1 LIMIT 25 OFFSET 0
         │
         ▼
Return: { files: [...], pagination: { total: 12345 } }
         │
         ▼
FileTree renders paginated table
```

## Design Decisions

### Why Subprocess Spawning?

**Alternatives considered:**
1. **Rewrite everything in TypeScript** - Would lose Python's system-level strengths
2. **Use Python for everything** - Would lose TypeScript's web development advantages
3. **Microservices with HTTP** - Overkill for this use case, adds latency
4. **gRPC or message queue** - Too complex for simple request-response pattern

**Why subprocess is best:**
- Simple request-response pattern
- No server management overhead
- Process isolation (Python crashes don't kill Node)
- JSON is sufficient for data exchange
- Easy to test components independently

### Why Shared SQLite Database?

**Alternatives considered:**
1. **Python REST API** - Adds unnecessary server complexity
2. **File-based JSON** - Poor query performance, no ACID
3. **Separate databases** - Synchronization nightmare

**Why SQLite is best:**
- Both languages have mature SQLite drivers
- ACID transactions
- Fast queries with indexes
- File-based (no server setup)
- Handles concurrent reads safely
- Write locking prevents conflicts

### Why Polling Instead of WebSockets?

**Rationale:**
- Simpler implementation
- No WebSocket server setup needed
- 2-second intervals are acceptable for scan progress
- Easier to debug
- Can upgrade to WebSockets later if needed

**When to upgrade:**
- Real-time progress (subsecond updates)
- Multiple concurrent users
- Server-push notifications

### Why Material-UI?

**Rationale:**
- Consistent with `@myorg/dashboard-ui` package
- Well-tested component library
- Responsive by default
- Good TypeScript support
- Extensive documentation

### Why Vite Instead of Webpack?

**Rationale:**
- Faster dev server startup
- Hot module replacement (HMR) works better
- Simpler configuration
- Modern ES modules
- Better TypeScript integration

## Security Considerations

### Path Traversal Prevention

**Issue**: User-supplied drive paths could access unauthorized directories

**Mitigation**:
- Python drive validator checks path existence
- Whitelisting of allowed mount points (/mnt/*)
- Path normalization before scanning

### Command Injection Prevention

**Issue**: Drive paths passed to Python could contain shell commands

**Mitigation**:
- Arguments passed as array (not shell string)
- `spawn()` with array prevents shell interpolation
- Python receives arguments directly (no shell evaluation)

**Example:**
```typescript
// Safe: Arguments as array
spawn(pythonPath, [scriptPath, drivePath]);

// Unsafe: Would allow injection
spawn(pythonPath, `${scriptPath} ${drivePath}`, { shell: true });
```

### Database Access Control

**Current**: Single-user local application

**Future**: For multi-user deployment:
- API authentication middleware
- User-specific scan isolation
- Role-based access control

## Performance Optimization

### Database Indexes

```sql
CREATE INDEX idx_files_extension ON files(extension);
CREATE INDEX idx_files_scan_path ON files(scan_id, path);
CREATE INDEX idx_files_size ON files(size_bytes);
CREATE INDEX idx_files_modified ON files(modified_date);
```

### Batch Inserts

Python scanner inserts files in batches of 100:
```python
def insert_files_batch(self, scan_id: int, files: List[Dict]):
    conn.executemany("INSERT INTO files ...", files)
```

### Pagination

File browsing uses `LIMIT` and `OFFSET`:
```sql
SELECT * FROM files
WHERE scan_id = ?
LIMIT ? OFFSET ?
```

### Connection Pooling

**TypeScript**: Single `better-sqlite3` instance per server
**Python**: Context managers for automatic connection cleanup

## Testing Strategy

### Unit Tests

**TypeScript**:
- DatabaseService methods
- PythonBridge error handling
- API route logic

**Python**:
- File scanner with mock filesystem
- Drive validator edge cases
- OS detector for various OS types

### Integration Tests

- TypeScript → Python subprocess communication
- Database writes from Python, reads from TypeScript
- End-to-end scan workflow
- API endpoint responses

### Manual Tests

- Scan actual drives
- Browse large file lists
- Test real-time progress updates
- Hardware detection on real drives

## Deployment Considerations

### Production Build

```bash
# Build TypeScript
npm run build

# Build frontend
npm run build:frontend

# Output:
# - dist/ (backend JavaScript)
# - dist-frontend/ (static HTML/JS/CSS)
```

### Environment Variables

```env
NODE_ENV=production
PORT=3001
DB_PATH=./output/archive.db
PYTHON_PATH=./python/venv/bin/python3
```

### System Requirements

- Node.js 20+
- Python 3.6+
- SQLite3
- 100MB disk space (plus storage for database)
- Linux/WSL (for PowerShell integration)

### Scaling Considerations

**Current**: Single-user desktop application

**For multi-user deployment**:
1. Add authentication layer
2. Implement WebSockets for progress
3. Queue system for scan jobs
4. Consider PostgreSQL instead of SQLite
5. Separate API server from UI server
6. Add Redis for session storage

## Future Enhancements

### Phase 6+ Ideas

1. **Virtual scrolling** for large file lists (react-window)
2. **Search functionality** with full-text search
3. **File deduplication** detection
4. **Drive comparison** tool
5. **Export to CSV/Excel**
6. **Drive statistics dashboard** with charts
7. **Scheduled scans** with cron
8. **Cloud backup** of database
9. **Mobile app** using React Native
10. **Docker container** for easy deployment

## Conclusion

The polyglot two-tier architecture successfully combines:
- TypeScript's web development strengths (API, UI)
- Python's system-level capabilities (scanning, hardware)
- Clean separation of concerns
- Simple integration via JSON subprocess
- Shared database for persistence

This design is maintainable, testable, and extensible while keeping each language in its "zone of excellence."

---

**Document Version**: 1.0
**Last Updated**: October 20, 2025
**Status**: Complete
