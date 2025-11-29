# Windows Index Metadata Extraction

This directory contains scripts to extract file metadata from Windows Search Index for your drive inventory project.

## Why Use Windows Search Index?

When Windows indexes a drive, it collects extensive metadata about files including:
- File paths, names, sizes, dates
- File types, extensions, MIME types  
- Document properties (author, title, etc.)
- Media metadata (dimensions, duration, etc.)
- Executable information (version, company, etc.)

This is much faster than manually scanning the drive since Windows has already done the work.

## Scripts

### 1. `quick_directory_extract.py` (Recommended)
Fast extraction focused on directory structure and file counts.

**What it extracts:**
- Directory tree with file counts and sizes
- File extension distribution per directory
- Oldest and newest files per directory
- Hierarchical directory structure

**Output:**
- `drive_E_directories_[timestamp].json` - Flat directory list
- `drive_E_tree_[timestamp].json` - Hierarchical tree structure
- Console summary with top directories and file types

### 2. `get_windows_index_metadata.py` (Comprehensive)
Full metadata extraction with detailed file information.

**What it extracts:**
- Complete file metadata for every indexed file
- File properties, dates, ownership info
- Application-specific metadata
- Comprehensive statistics and analysis

**Output:**
- `drive_e_files_[timestamp].json` - Complete file listing
- `drive_e_directories_[timestamp].json` - Directory analysis  
- `drive_e_summary_[timestamp].json` - Summary statistics
- `output/windows_index.db` - SQLite database with all data

## Setup and Usage

### Option 1: Automated Setup (PowerShell)
```powershell
# From Windows PowerShell (not WSL):
.\setup_windows_extraction.ps1
```

### Option 2: Manual Setup
```bash
# Install required package
pip install pywin32

# Run quick extraction
python python/quick_directory_extract.py

# Or run full extraction  
python python/get_windows_index_metadata.py
```

## Requirements

1. **Windows OS** - These scripts use Windows COM interfaces
2. **Python with pywin32** - For accessing Windows Search Index
3. **Windows Search Service** - Must be running
4. **Drive E: connected** - And accessible to Windows

## Important Notes

- **Run from Windows, not WSL** - The scripts use Windows-specific COM interfaces
- **Retrieves existing index data** - No waiting! Gets whatever Windows has already indexed
- **Service dependency** - Windows Search service must be running
- **Performance** - Quick script is much faster for basic directory structure

## Troubleshooting

### "Cannot connect to Windows Search Index"
- Ensure Windows Search service is running
- Check that the drive is properly connected
- Verify Windows has already indexed the drive (should be immediate if connected for a while)

### "Module 'win32com' not found"  
- Install pywin32: `pip install pywin32`
- Ensure you're running from Windows Python, not WSL

### "No files found"
- Verify drive E: is connected and accessible
- Confirm Windows Search index contains data for this drive
- Try running as administrator

## Integration with Main Project

The output JSON files can be integrated into your main database:
- Import directory structures into your scanning pipeline
- Use as baseline for comparison with manual scans  
- Leverage metadata for file categorization and analysis

## Customization

To scan a different drive, modify the `drive_letter` variable in the scripts:
```python
drive_letter = "F"  # Change from "E" to your target drive
```