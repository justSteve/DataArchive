# NAS Consolidation Workflow (Z: → W:)

**⚠️ ARCHIVED - This workflow is outdated**

**Status**: W: drive no longer exists. NAS has been physically disassembled.
**Current State**: Multiple physical drives extracted (4TB WD Red, 1TB Blue, 2TB Black)
**Updated Docs**: See [NAS-DRIVE-INSPECTION.md](NAS-DRIVE-INSPECTION.md) for current drive status

---

**Quick Reference for Backup Consolidation with Duplicate Detection**

---

## Goal

Import backups from NAS (Z:) to target drive (W:), identify duplicates, and consolidate into cleansed catalog.

---

## Prerequisites

```bash
# Start dev environment
./start-dev.sh

# Verify both drives are accessible
ls Z:\  # or /mnt/z in WSL
ls W:\  # or /mnt/w in WSL
```

---

## Workflow Steps

### 1. Inspect Source Drive (Z:)

**Via Web UI:**
1. Open [http://localhost:5173](http://localhost:5173)
2. Click "Inspector" tab
3. Click "Start New Inspection"
4. Enter drive path: `Z:\` (Windows) or `/mnt/z` (WSL)
5. Click "Start Inspection"
6. **Skip Pass 1** (Health) - click "Skip" button
7. **Skip Pass 2** (OS Detection) - click "Skip" button
8. **Run Pass 3** (Metadata + Hashes) - click "Run Pass 3"
   - ⏳ This will take time for large drives (expect ~5-10 min per 100GB)
   - Progress visible in UI with file count
9. **Run Pass 4** (Review) - click "Run Pass 4"
   - Claude generates analysis report
10. Click "Complete Inspection"

**Via Beads (Recommended for tracking):**
```bash
bd create "Inspect Z: drive - NAS backup source" --type=task --priority=2
bd update <id> --status=in_progress

# ... run inspection via UI ...

bd close <id> --reason="Z: inspection complete - 245,832 files, 1.2TB"
```

---

### 2. Inspect Target Drive (W:)

**Repeat same process for W::**

```bash
bd create "Inspect W: drive - consolidation target" --type=task --priority=2
bd update <id> --status=in_progress
```

1. Click "Start New Inspection"
2. Enter: `W:\`
3. Skip Pass 1, Skip Pass 2
4. **Run Pass 3** - System automatically detects duplicates from Z:
5. Run Pass 4
6. Complete Inspection

```bash
bd close <id> --reason="W: inspection complete - 189,450 files, 800GB, cross-drive duplicates detected"
```

---

### 3. Review Claude's Analysis

**Reports Location:** `output/reports/`

**Two reports generated:**
- `session_1_<date>.md` - Z: drive analysis
- `session_2_<date>.md` - W: drive analysis (includes cross-drive duplicate summary)

**What to look for:**
- Duplicate groups sorted by wasted space
- Cross-scan duplicates (files on both Z: and W:)
- Decision points: "Keep Z: or W: version?"
- Recommended actions

---

### 4. Query Duplicates

**Find all cross-drive duplicates:**

```sql
SELECT
  fh1.file_path as z_path,
  fh2.file_path as w_path,
  fh1.file_size as size_bytes,
  ROUND(fh1.file_size / 1024.0 / 1024.0, 2) as size_mb
FROM file_hashes fh1
JOIN file_hashes fh2
  ON fh1.quick_hash = fh2.quick_hash
  AND fh1.file_size = fh2.file_size
  AND fh1.scan_id != fh2.scan_id
JOIN scans s1 ON fh1.scan_id = s1.scan_id
JOIN scans s2 ON fh2.scan_id = s2.scan_id
WHERE s1.mount_point LIKE 'Z:%'
  AND s2.mount_point LIKE 'W:%'
ORDER BY fh1.file_size DESC
LIMIT 100;
```

**Find largest duplicate groups:**

```sql
SELECT
  dg.group_id,
  dg.file_size,
  dg.member_count,
  ROUND(dg.wasted_bytes / 1024.0 / 1024.0 / 1024.0, 2) as wasted_gb,
  fh.file_path as example_path
FROM duplicate_groups dg
JOIN file_hashes fh ON dg.group_id = fh.duplicate_group_id
WHERE dg.member_count > 1
GROUP BY dg.group_id
ORDER BY dg.wasted_bytes DESC
LIMIT 50;
```

**Export duplicate paths for scripted deletion:**

```sql
-- Export to CSV for review
.mode csv
.output z_duplicates_to_delete.csv

SELECT
  fh.file_path,
  fh.file_size,
  dg.group_id,
  dg.member_count
FROM file_hashes fh
JOIN duplicate_groups dg ON fh.duplicate_group_id = dg.group_id
JOIN scans s ON fh.scan_id = s.scan_id
WHERE s.mount_point LIKE 'Z:%'
  AND dg.member_count > 1
ORDER BY dg.wasted_bytes DESC;

.output stdout
```

---

### 5. Consolidation Actions

**Option A: Manual Review (Safest)**

1. Open `z_duplicates_to_delete.csv` in Excel
2. Filter by file type, size, or path patterns
3. Manually verify files before deletion
4. Delete via Explorer or PowerShell

**Option B: Scripted Deletion (Faster)**

```powershell
# PowerShell script to delete duplicates (DRY RUN FIRST)
$duplicates = Import-Csv "z_duplicates_to_delete.csv"

# DRY RUN - just show what would be deleted
foreach ($file in $duplicates) {
    $path = $file.file_path
    if (Test-Path $path) {
        Write-Host "Would delete: $path ($($file.file_size) bytes)"
    } else {
        Write-Host "NOT FOUND: $path"
    }
}

# ACTUAL DELETION (remove -WhatIf to execute)
foreach ($file in $duplicates) {
    $path = $file.file_path
    if (Test-Path $path) {
        Remove-Item $path -WhatIf
    }
}
```

**Option C: Archive Before Delete**

```powershell
# Move duplicates to archive folder instead of deleting
$archiveRoot = "W:\__duplicates_archive"
New-Item -ItemType Directory -Path $archiveRoot -Force

foreach ($file in $duplicates) {
    $path = $file.file_path
    if (Test-Path $path) {
        $relativePath = $path -replace '^Z:\\', ''
        $archivePath = Join-Path $archiveRoot $relativePath
        $archiveDir = Split-Path $archivePath -Parent

        New-Item -ItemType Directory -Path $archiveDir -Force
        Move-Item $path $archivePath
        Write-Host "Archived: $path -> $archivePath"
    }
}
```

---

## Decision Matrix

### When to Keep Z: Version

- Z: has newer modification date
- Z: is larger file size (may have higher quality)
- Z: has better folder organization

### When to Keep W: Version

- W: already has other related files (keep group together)
- W: has better naming convention
- W: is already in target folder structure

### When to Keep Both

- Files have same name but different content (hash mismatch)
- Uncertain which is "correct" version
- Archival policy requires redundancy

---

## Progress Tracking with Beads

```bash
# Phase 1: Inspection
bd create "Phase 1: Inspect Z: and W: drives" --type=task
bd update <id> --status=in_progress
# ... run inspections ...
bd close <id> --reason="Both drives inspected, 245k files on Z:, 189k on W:"

# Phase 2: Analysis
bd create "Phase 2: Analyze duplicate groups" --type=task
bd update <id> --status=in_progress
# ... review Claude reports and run SQL queries ...
bd close <id> --reason="Found 45k duplicates, 200GB wasted space"

# Phase 3: Consolidation
bd create "Phase 3: Delete/archive duplicates from Z:" --type=task
bd update <id> --status=in_progress
# ... execute deletion/archival scripts ...
bd close <id> --reason="Removed 45k duplicates, reclaimed 200GB"

# Phase 4: Final Sync
bd create "Phase 4: Sync remaining Z: files to W:" --type=task
bd update <id> --status=in_progress
# ... copy remaining files ...
bd close <id> --reason="Consolidation complete, W: now has 289k files"
```

---

## Expected Timeline

### Drive Sizes and Time Estimates

| Drive | Size | Files | Pass 3 Time | Pass 4 Time |
|-------|------|-------|-------------|-------------|
| Z: (NAS) | 1.2TB | ~250k | 30-40 min | 2-5 min |
| W: (Target) | 800GB | ~190k | 20-30 min | 2-5 min |

**Total inspection time:** ~60-90 minutes
**Analysis time:** 30-60 minutes (reviewing reports, writing queries)
**Consolidation time:** Varies (manual review can take hours, scripted deletion ~10-20 min)

---

## Safety Checklist

Before executing any deletions:

- [ ] Both drives inspected successfully
- [ ] Pass 3 completed for both drives
- [ ] Reports reviewed in `output/reports/`
- [ ] SQL queries validated with `LIMIT 10` first
- [ ] Export CSV reviewed manually
- [ ] Dry-run script tested with `-WhatIf`
- [ ] Backup of critical files (if any)
- [ ] Beads tracking in place for rollback reference

---

## Troubleshooting

### "Cross-drive duplicates not showing up"

**Check:**
1. Both inspections used Pass 3
2. Both inspections completed successfully
3. Query includes correct scan IDs:
   ```sql
   SELECT scan_id, mount_point FROM scans ORDER BY scan_id DESC LIMIT 5;
   ```

### "File counts don't match between UI and database"

**Solution:**
- Refresh browser (UI caches data)
- Re-run query:
  ```sql
  SELECT COUNT(*) FROM files WHERE scan_id = <id>;
  ```

### "PowerShell script failing with access denied"

**Solution:**
- Run PowerShell as Administrator
- Check file permissions: `Get-Acl Z:\path\to\file`
- Use `-Force` flag: `Remove-Item $path -Force`

---

## Success Metrics

**After consolidation:**

- [ ] Z: drive duplicates removed/archived
- [ ] W: drive has all unique files from both drives
- [ ] Database has clean file catalog
- [ ] Reports saved for audit trail
- [ ] Beads closed with final statistics
- [ ] Free space reclaimed matches expectations

**Example success message:**
```
Consolidation complete!
- Source (Z:): 245,832 files → 200,515 files (45k duplicates removed)
- Target (W:): 189,450 files → 289,963 files (100k files added from Z:)
- Space reclaimed: 200GB
- Total catalog: 289,963 unique files across 1.6TB
```

---

**Last Updated:** 2026-03-03
**For:** NAS backup consolidation (Z: → W:)
