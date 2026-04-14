# Lessons Learned - DataArchive Hash Implementation

**Date:** 2026-03-06
**Bead:** DataArchive-f8m
**Context:** Adding file hashing support and scanning Z: drive

## What Worked

### 1. Modular Architecture

- Separating hash utilities (`utils/hash_utils.py`) from scanning logic worked well
- Database schema extension via ALTER TABLE allowed backward compatibility
- Cross-platform compatibility via `shutil.disk_usage()` instead of Unix-specific `os.statvfs()`

### 2. Two-Tier Hashing Strategy

- **Quick hash** (MD5 of size + first/last chunks) for fast preliminary duplicate detection
- **SHA-256** for definitive content verification
- This approach balances speed with accuracy

### 3. Background Processing

- Running scans as background tasks allows long-running operations
- JSON output mode provides structured data for programmatic consumption
- Progress bars (tqdm) give real-time feedback

## What Didn't Work (And Fixes)

### 1. Unicode Encoding Issues

**Problem:** Windows console (cp1252 encoding) couldn't handle Unicode checkmark characters (✓)

**Root Cause:**
- Logger outputting Unicode characters to stdout
- Windows CMD defaults to cp1252 encoding
- Python's logger didn't handle encoding gracefully

**Solution:**
- Removed all Unicode checkmarks from log messages
- Used simple ASCII characters instead
- Could alternatively set `PYTHONIOENCODING=utf-8` but this requires environment setup

**Lesson:** Avoid Unicode in console output on Windows unless you control the environment

### 2. Platform-Specific System Calls

**Problem:** `os.statvfs()` doesn't exist on Windows

**Root Cause:**
- DriveManager was designed primarily for WSL (Windows Subsystem for Linux)
- Used Unix-specific system call without Windows fallback

**Solution:**
- Replaced `os.statvfs()` with `shutil.disk_usage()`
- `shutil.disk_usage()` is cross-platform and works on both Windows and Unix

**Lesson:** Always use cross-platform stdlib functions when available:
- ✅ `shutil.disk_usage()` - works everywhere
- ❌ `os.statvfs()` - Unix only
- ❌ `win32api` - Windows only

### 3. Context Manager Complications

**Problem:** `prevent_sleep()` context manager caused Unicode issues in cleanup

**Root Cause:**
- Power manager was using Unicode checkmarks in its cleanup logging
- Context manager errors are harder to debug than regular function calls

**Solution:**
- Removed `prevent_sleep()` for this use case
- Background tasks don't need sleep prevention (system stays awake anyway)

**Lesson:** Consider whether context managers add value. For background tasks, system sleep isn't a concern.

## Performance Observations

### Scan Performance (Z: Drive)

- **Files:** 189,345 total
- **Speed:** 8-12 files/second with SHA-256 hashing
- **Time:** ~6 hours estimated for full scan
- **Bottleneck:** SHA-256 computation (CPU-bound, not I/O-bound)

### Optimization Opportunities

1. **Parallel hashing** - Could use multiprocessing to hash multiple files simultaneously
2. **Quick hash first** - Scan with quick hash, then SHA-256 only potential duplicates
3. **Incremental scans** - Skip files that haven't changed since last scan
4. **Database indexing** - Add indexes on hash columns for faster duplicate queries

## Architecture Decisions

### Why Not Use Existing Inspection System?

The multi-pass inspection system (`python/inspection/`) exists but:
- Designed for comprehensive drive analysis (health checks, OS detection, etc.)
- More complex than needed for simple file cataloging
- `scan_and_hash.py` is simpler, focused tool for this specific use case

### Database Schema Extension

Added columns to existing `files` table rather than creating new table:
```sql
ALTER TABLE files ADD COLUMN quick_hash TEXT
ALTER TABLE files ADD COLUMN sha256_hash TEXT
```

**Pros:**
- Backward compatible
- No migration needed
- Existing queries still work

**Cons:**
- NULL values for old scans
- Can't enforce NOT NULL constraint

**Better approach for greenfield:**
- Include hash columns in initial schema
- Or create separate `file_hashes` table with FK to `files`

## Windows Boot Drive Deduplication Strategy

### Context

User has multiple Windows boot drives in closet. Goal is to:
1. Catalog all files with hashes
2. Identify duplicates
3. Preserve user files, allow overlap in Windows system files
4. Priority is complete record, not space minimization

### Approach

#### Phase 1: Catalog Everything (Current)

- Scan all drives with SHA-256 hashing
- Build complete inventory in database
- No deletion yet - gathering data first

#### Phase 2: Analysis (Next)

Query duplicate files:
```sql
SELECT sha256_hash, COUNT(*) as count,
       GROUP_CONCAT(path || ' [scan_id:' || scan_id || ']', '; ') as locations,
       size_bytes
FROM files
WHERE sha256_hash IS NOT NULL
GROUP BY sha256_hash
HAVING count > 1
ORDER BY (count * size_bytes) DESC;
```

#### Phase 3: Classification

Distinguish file types:
1. **Windows system files** - Can be identified by path patterns:
   - `Windows\System32\*`
   - `Windows\WinSxS\*`
   - `Program Files\*`
   - Standard Windows binaries (known hashes)

2. **User files** - Everything else:
   - `Users\Steve\*`
   - `ProgramData\*` (some)
   - Non-standard locations

#### Phase 4: Smart Deduplication

**Rules:**
- **Windows system files:** Keep one copy per version, document locations
- **User files:** Never auto-delete - flag for manual review
- **Identical user files:** Present to user with context (dates, paths)
- **Large duplicates first:** Sort by `(count * size_bytes)` to get biggest wins

### Implementation Plan

Create scripts:
1. `analyze_duplicates.py` - Generate duplicate reports
2. `classify_files.py` - Categorize Windows vs. user files
3. `review_duplicates.py` - Interactive review tool

## Next Steps

### Immediate (Current Scan)

- ✅ Z: drive scan running (8% complete)
- ⏳ Wait for completion (~5 hours)
- 📝 Verify results in database

### Next Phase (Remaining Drives)

1. **Inventory drives** - List all drives in closet
2. **Scan each drive** - Use `scan_and_hash.py` with SHA-256
3. **Track metadata** - Note physical labels, dates, any identifying info
4. **Build catalog** - Complete database of all files across all drives

### Future Enhancements

1. **Parallel scanning** - Can scan multiple drives simultaneously
2. **Web UI** - React frontend for browsing catalog
3. **Duplicate analysis** - Query tools for finding duplicates
4. **Smart cleanup** - Interactive tools for reviewing and removing duplicates
5. **MCP server** - Expose query API for Claude to access catalog

## Key Takeaways

1. **Start simple** - `scan_and_hash.py` was easier than extending inspection system
2. **Test on Windows** - WSL-focused code doesn't always work on native Windows
3. **Avoid Unicode** - ASCII is safest for console output on Windows
4. **Use stdlib** - Cross-platform functions prevent platform-specific bugs
5. **Background tasks** - Long-running operations should run async
6. **Document as you go** - These lessons are fresh now, will be fuzzy later

---

*This document captures real-world learnings from implementing file hashing. Update it as we encounter new challenges and solutions.*
