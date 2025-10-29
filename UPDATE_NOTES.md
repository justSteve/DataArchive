# Update Summary - Sleep Prevention & Error Handling

## Issues Addressed

### 1. System Sleep During Long Scans
**Problem**: The workstation could go to sleep during long scanning operations, interrupting the scan.

**Solution**: Implemented a power management system that:
- Automatically prevents Windows from sleeping when running in WSL
- Uses PowerShell's SetThreadExecutionState Windows API call
- Implemented as a Python context manager (similar to C#'s `using` statement)
- Automatically restores normal power management when scan completes or crashes
- Falls back gracefully if PowerShell is not available

**Files Added**:
- `utils/power_manager.py` - Power management implementation
- `utils/__init__.py` - Package initializer

**Files Modified**:
- `scan_drive.py` - Wrapped main scanning logic with `prevent_sleep()` context manager

**Usage**: Automatic - no user intervention needed. The scan prevents sleep when it starts and restores normal behavior when it ends.

### 2. Excessive Error Logging for Inaccessible Files
**Problem**: WSL cannot access certain Windows system files (pagefile.sys, *.edb files, etc.), causing:
- Excessive ERROR-level log messages
- Scan appeared to process 0 files despite finding 915,600
- Progress bar not updating properly

**Solution**: Improved error handling:
- Changed inaccessible file logging from ERROR to DEBUG level (reduces noise)
- Files that can't be accessed are now counted but skipped gracefully
- Progress bar updates for both successful and skipped files
- Separated expected errors (PermissionError, OSError) from unexpected errors
- Added proper error counting and reporting

**Files Modified**:
- `core/file_scanner.py` - Improved error handling and logging

## Technical Details

### Power Management Architecture

```python
# Context manager pattern (like C# using statement)
with prevent_sleep():
    # Long-running operation
    scan_drive()
# Sleep automatically restored here, even if exception occurs
```

The `PowerManager` class:
1. Detects if running in WSL by checking `/proc/version`
2. Creates a PowerShell script that calls Windows kernel32.dll
3. Launches the script in the background
4. Script keeps executing until Python process terminates
5. Automatically cleaned up via context manager

### Error Handling Strategy

```python
# Before: All errors logged at ERROR level, returned None, progress didn't update
# After: Graceful handling with appropriate log levels

try:
    file_info = self._get_file_info(filepath)
    if file_info:
        yield file_info
        file_count += 1
    else:
        # File was inaccessible - counted but skipped
        self.error_count += 1
    
    # Progress bar always updates
    if show_progress:
        pbar.update(1)
except (PermissionError, OSError):
    # Expected errors in WSL - log at DEBUG level
    logger.debug(f"Skipped inaccessible file")
except Exception:
    # Unexpected errors - log at WARNING level
    logger.warning(f"Unexpected error")
```

## Testing Recommendations

1. **Run a test scan**:
   ```bash
   ./dataarchive /mnt/c/Windows/System32
   ```
   Expected behavior:
   - Should see "System sleep prevention activated"
   - Should skip inaccessible system files without excessive ERROR messages
   - Progress bar should update continuously
   - Should process accessible files successfully
   - Should see "System sleep prevention deactivated" at end

2. **Verify sleep prevention**:
   - Start a long scan
   - Check Task Manager for PowerShell process running prevent_sleep.ps1
   - Wait past your normal sleep timeout
   - System should remain awake

3. **Test interruption handling**:
   - Start a scan
   - Press Ctrl+C
   - Verify sleep prevention is properly restored

## For .NET Developers

These changes implement patterns you're familiar with:

1. **Context Manager** = `using` statement
   - Ensures resources are always cleaned up
   - Even if exceptions occur
   - RAII pattern (Resource Acquisition Is Initialization)

2. **Error Classification** = Exception hierarchy
   - Expected exceptions (PermissionError) = handled gracefully
   - Unexpected exceptions = logged with more detail
   - Similar to catching specific vs general exceptions in C#

3. **Logging Levels** = Trace/Debug/Info/Warning/Error
   - DEBUG = Detailed diagnostic info
   - INFO = Normal operation events
   - WARNING = Unexpected but handled issues
   - ERROR = Actual problems requiring attention

## Next Steps

Run the updated installer to get these changes:
```bash
cd /mnt/c/Users/steve/OneDrive/Code/DataArchive
./install.sh
./dataarchive /mnt/e
```

The scan should now:
- Run without your system sleeping
- Handle inaccessible files gracefully
- Provide clean, readable output
- Actually process files (not 0 files)
