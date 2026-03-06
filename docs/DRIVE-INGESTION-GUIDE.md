# Drive Ingestion Guide - DataArchive v2

**Updated:** 2026-03-05
**Use Case:** Drive cataloging, duplicate detection, and consolidation

## Current System State

DataArchive v2 is **fully implemented** with two ingestion workflows:

1. **v1 Legacy Scan** - Fast, blocking file catalog (preserved for compatibility)
2. **v2 Inspection Workflow** - Multi-pass interactive analysis with Claude assistance

### Database Schema

**Location:** `output/archive.db`

**Core Tables (v1):**
- `drives` - Physical drive hardware records
- `scans` - Scan session tracking
- `files` - File metadata catalog
- `os_info` - Operating system detection
- `scan_statistics` - Aggregate statistics

**Inspection Tables (v2):**
- `inspection_sessions` - Multi-pass workflow tracking
- `inspection_passes` - Per-pass results and reports
- `inspection_decisions` - User/Claude decisions
- `file_hashes` - Duplicate detection (quick_hash + SHA-256)

---

## Two Ingestion Workflows

### Workflow 1: v1 Legacy Scan (Fast Catalog)

**Best for:** Quick cataloging when you just need a file inventory.

**What it does:**
- Enumerates all files and folders
- Captures metadata (size, dates, extensions)
- Detects hardware info and OS
- Writes directly to `files` table

**How to use:**

**Via Python CLI:**
```bash
cd python
venv\Scripts\activate
python scan_drive.py Z:\ --db ../output/archive.db --json-output
```

**Via Web UI:**
1. Start dev servers: `./start-dev.sh`
2. Navigate to [http://localhost:5173](http://localhost:5173)
3. Go to "Drive Scanner" tab
4. Enter drive path: `Z:\`
5. Click "Start Scan"

**Output:**
- Files written to `files` table with `scan_id`
- Hardware written to `drives` table
- OS info written to `os_info` table (if detected)

---

### Workflow 2: v2 Inspection (Multi-Pass with Claude)

**Best for:** Deep analysis with duplicate detection and decision support.

**What it does:**
- **Pass 1: Health Check** - chkdsk + SMART data (optional, can skip)
- **Pass 2: OS Detection** - Registry/pattern matching (optional, can skip)
- **Pass 3: Metadata Capture** - Full scan + quick hash + SHA-256 + duplicate detection
- **Pass 4: Interactive Review** - Claude analyzes results and presents decision points

**How to use:**

**Via Web UI (Recommended):**
1. Start dev servers: `./start-dev.sh`
2. Navigate to [http://localhost:5173](http://localhost:5173)
3. Go to "Inspector" tab
4. Click "Start New Inspection"
5. Enter drive path: `Z:\` (or `/mnt/z` if in WSL)
6. Click "Start Inspection"
7. **Wizard appears** - click "Run Pass 1" or "Skip" for each pass
8. After Pass 4, review Claude's decision report
9. Click "Complete Inspection"

**Via API:**
```bash
# Start inspection
curl -X POST http://localhost:3001/api/inspections/start \
  -H "Content-Type: application/json" \
  -d '{"drivePath": "Z:\\"}'

# Returns: {"success": true, "session_id": 1, ...}

# Run Pass 1 (Health)
curl -X POST http://localhost:3001/api/inspections/1/pass/1/start

# Run Pass 2 (OS) - or skip
curl -X POST http://localhost:3001/api/inspections/1/pass/2/start

# Run Pass 3 (Metadata + Duplicates) - CRITICAL for your use case
curl -X POST http://localhost:3001/api/inspections/1/pass/3/start

# Run Pass 4 (Review + Claude analysis)
curl -X POST http://localhost:3001/api/inspections/1/pass/4/start

# Complete
curl -X POST http://localhost:3001/api/inspections/1/complete
```

**Output:**
- Files written to `files` table with `scan_id`
- Hashes written to `file_hashes` table
- Claude report written to `output/reports/session_<id>_<date>.md`
- Decision points tracked in `inspection_decisions` table

---

## Your Use Case: NAS Consolidation (Z: → W:)

### Recommended Workflow

Since you're **consolidating backups with lots of duplicates**, use the **v2 Inspection Workflow** for both drives:

#### Step 1: Inspect Source Drive (Z:)

```bash
# Start inspection via web UI or API
POST /api/inspections/start {"drivePath": "Z:\\"}

# Run all 4 passes (skip Pass 1/2 if not relevant)
# Pass 3 is CRITICAL - captures hashes for duplicate detection
```

**After Pass 3 completes:**
- All files from Z: are cataloged
- Quick hashes computed for all files >1KB
- SHA-256 computed for suspected duplicates
- Database now has baseline for comparison

#### Step 2: Inspect Target Drive (W:)

```bash
# Start second inspection
POST /api/inspections/start {"drivePath": "W:\\"}

# Run Pass 3 (metadata + duplicates)
# The system will automatically detect cross-drive duplicates
```

**Pass 3 cross-scan duplicate detection:**
- Compares quick_hash against ALL files in `file_hashes` table
- Identifies files that exist on both Z: and W:
- Flags them as `is_cross_scan: true`

#### Step 3: Review Claude's Analysis

After both inspections complete:

1. Read Claude reports in `output/reports/`
2. Review duplicate groups:
   - Within-drive duplicates (same scan_id)
   - Cross-drive duplicates (different scan_id)
3. Claude will present decision points:
   - "Keep Z: or W: version?"
   - "Delete duplicates or keep one copy?"
   - "Archive originals before deletion?"

#### Step 4: Query Duplicates Directly

```sql
-- Find all duplicate groups across both drives
SELECT
  dg.group_id,
  dg.quick_hash,
  dg.file_size,
  COUNT(DISTINCT fh.scan_id) as scan_count,
  GROUP_CONCAT(fh.file_path) as paths
FROM duplicate_groups dg
JOIN file_hashes fh ON dg.group_id = fh.duplicate_group_id
GROUP BY dg.group_id
HAVING scan_count > 1
ORDER BY dg.wasted_bytes DESC;

-- Find cross-drive duplicates only
SELECT
  fh1.file_path as z_path,
  fh2.file_path as w_path,
  fh1.file_size as size_bytes,
  fh1.quick_hash
FROM file_hashes fh1
JOIN file_hashes fh2
  ON fh1.quick_hash = fh2.quick_hash
  AND fh1.scan_id != fh2.scan_id
WHERE fh1.scan_id = (SELECT scan_id FROM scans WHERE mount_point LIKE 'Z:%' LIMIT 1)
  AND fh2.scan_id = (SELECT scan_id FROM scans WHERE mount_point LIKE 'W:%' LIMIT 1);
```

---

## Duplicate Detection Deep Dive

### How It Works

**Pass 3 (`python/inspection/pass3_metadata.py`):**

1. **Enumerate files** - Walks directory tree
2. **Compute quick_hash** - Fast hash of first 64KB + last 64KB + file size
   - Purpose: 99.9% accurate for duplicate detection
   - Speed: ~1000x faster than full SHA-256
3. **Batch insert** to `files` table
4. **Detect duplicates within scan:**
   - Group by `(file_size, quick_hash)`
   - Files with same tuple are duplicates
5. **Detect duplicates across scans:**
   - Query existing `file_hashes` table
   - Match on `quick_hash` from previous scans
6. **Verify with SHA-256** (optional):
   - Compute full hash for duplicate groups
   - Confirm 100% certainty
7. **Write to `file_hashes` table:**
   ```sql
   INSERT INTO file_hashes (
     file_id, scan_id, file_path, file_size,
     quick_hash, sha256_hash, duplicate_group_id
   ) VALUES (...)
   ```

### Duplicate Group Schema

```sql
CREATE TABLE duplicate_groups (
  group_id INTEGER PRIMARY KEY AUTOINCREMENT,
  quick_hash TEXT NOT NULL,
  file_size INTEGER NOT NULL,
  member_count INTEGER,
  wasted_bytes INTEGER,  -- (member_count - 1) * file_size
  sha256_verified BOOLEAN DEFAULT 0,
  created_at TIMESTAMP
);

CREATE TABLE file_hashes (
  hash_id INTEGER PRIMARY KEY AUTOINCREMENT,
  file_id INTEGER NOT NULL,
  scan_id INTEGER NOT NULL,
  file_path TEXT NOT NULL,
  file_size INTEGER NOT NULL,
  quick_hash TEXT NOT NULL,
  sha256_hash TEXT,
  duplicate_group_id INTEGER,
  is_cross_scan BOOLEAN DEFAULT 0,
  FOREIGN KEY (duplicate_group_id) REFERENCES duplicate_groups(group_id)
);
```

---

## Platform Considerations

### Windows (Native)

**Drive paths:** `Z:\`, `W:\`

```bash
# Python CLI
cd python
venv\Scripts\activate
python scan_drive.py Z:\ --db ../output/archive.db --json-output

# Web UI (works out of box)
./start-dev.sh
# Navigate to http://localhost:5173
```

### WSL (Windows Subsystem for Linux)

**Drive paths:** `/mnt/z`, `/mnt/w`

**Challenge:** Hardware detection requires PowerShell

**Solution:** PythonBridge auto-detects WSL and calls PowerShell via:
```bash
powershell.exe -Command "Get-WmiObject Win32_DiskDrive | Select Model, SerialNumber ..."
```

**Registry access:** Use `python/utils/registry_reader.py` which wraps PowerShell

---

## Practical Recommendations

### For Your NAS Consolidation

1. **Run v2 Inspection on both drives**
   - Use Pass 3 (Metadata) for both Z: and W:
   - Skip Pass 1/2 if health and OS aren't relevant

2. **Let Claude analyze**
   - Pass 4 generates report with decision points
   - Reviews duplicate groups by wasted space (largest first)
   - Suggests actions: keep, delete, archive

3. **Use beads for tracking**
   ```bash
   bd create "Inspect Z: drive (NAS backup source)" --type=task
   bd update <id> --status=in_progress
   bd close <id> --reason="Inspection complete, 1.2TB cataloged"

   bd create "Inspect W: drive (consolidation target)" --type=task
   bd update <id> --status=in_progress
   bd close <id> --reason="Inspection complete, 800GB cataloged, 200GB duplicates found"
   ```

4. **Query database for surgical operations**
   - Don't rely solely on Claude's report
   - Write custom SQL to find specific patterns
   - Example: "All .mp4 files >500MB with duplicates"

5. **Dry-run deletions**
   - Export duplicate file paths to text file
   - Review manually before scripting deletions
   - Use PowerShell `Test-Path` to verify before `Remove-Item`

---

## Next Steps

### Quick Start Commands

```bash
# 1. Start dev environment
./start-dev.sh

# 2. Open browser
http://localhost:5173

# 3. Click "Inspector" tab

# 4. Start inspection for Z:
#    - Enter: Z:\ (or /mnt/z if WSL)
#    - Click "Start New Inspection"
#    - Run Pass 3 (Metadata + Duplicates)
#    - Run Pass 4 (Review)

# 5. Repeat for W:

# 6. Review reports in output/reports/

# 7. Query duplicates via SQLite
sqlite3 output/archive.db
```

### Development Commands

```bash
# Check database contents
npm run db:query "SELECT COUNT(*) FROM inspection_sessions"
npm run db:query "SELECT * FROM inspection_sessions WHERE status='active'"

# Reset database (CAUTION: destroys all data)
./quick-reset-db.sh

# View logs
tail -f python/logs/scan.log
```

---

## Troubleshooting

### "Drive validation failed"

**Problem:** PythonBridge can't detect drive hardware

**Solution:**
- Ensure drive is mounted and accessible
- Check permissions (may need admin/sudo)
- WSL: Verify `/mnt/z` exists: `ls /mnt/z`

### "Pass 3 running forever"

**Problem:** Large drive (>1TB) takes time

**Solution:**
- Check progress in `python/logs/scan.log`
- Monitor file count in database:
  ```sql
  SELECT COUNT(*) FROM files WHERE scan_id = <session_scan_id>;
  ```
- Expected speed: ~5000 files/minute (varies by drive speed)

### "Duplicate detection not working"

**Problem:** `file_hashes` table empty

**Solution:**
- Ensure Pass 3 completed successfully
- Check `inspection_passes` table:
  ```sql
  SELECT * FROM inspection_passes WHERE pass_number = 3 AND status = 'completed';
  ```
- If status is 'failed', check `error_message` column

### "Claude report is empty"

**Problem:** Pass 4 didn't generate report

**Solution:**
- Check `output/reports/` directory
- Verify Pass 3 completed first (Pass 4 depends on Pass 3 data)
- Check API logs: `npm run api` (should see report generation messages)

---

## References

- **Main README:** [README.md](../README.md)
- **CLAUDE.md:** [CLAUDE.md](../CLAUDE.md) - Project instructions for Claude Code
- **Database Schema:** [python/core/database.py](../python/core/database.py#L40-L150)
- **Inspection Routes:** [src/api/routes/inspections.ts](../src/api/routes/inspections.ts)
- **InspectionWizard UI:** [src/frontend/components/InspectionWizard.tsx](../src/frontend/components/InspectionWizard.tsx)
- **Pass 3 (Metadata):** [python/inspection/pass3_metadata.py](../python/inspection/pass3_metadata.py)
- **Pass 4 (Review):** [python/inspection/pass4_review.py](../python/inspection/pass4_review.py)

---

**Last Updated:** 2026-03-03
**DataArchive Version:** v2 (Multi-pass inspection workflow)
