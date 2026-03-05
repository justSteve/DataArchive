# NAS Drive Inspection - Physical Connection

**Date**: 2026-03-05
**Drive**: WDC WD40EFRX-68WT0N0 (4TB WD Red NAS drive)
**Status**: Physically connected via SATA (PHYSICALDRIVE2)
**Previous Location**: NAS Z: drive

## Drive Layout

**Physical Drive**: `\\.\PHYSICALDRIVE2`
**Model**: WDC WD40EFRX-68WT0N0
**Capacity**: 4TB (4,000,784,417,280 bytes)
**Partitions**: 8 total

### Partition Table

| Partition | Drive Letter | Size   | Type    | Filesystem | Notes                    |
|-----------|--------------|--------|---------|------------|--------------------------|
| 1         | -            | 2 GB   | Unknown | -          | Likely Linux boot        |
| 2         | -            | 2 GB   | Unknown | -          | Likely Linux swap        |
| 3         | E:           | 512 MB | Basic   | ext4?      | Small system partition   |
| 4         | K:           | 3.7 TB | Basic   | ext4?      | **Main data partition**  |
| 5         | G:           | 99 MB  | Basic   | ext4?      | -                        |
| 6         | H:           | 100 MB | Basic   | ext4?      | -                        |
| 7         | I:           | 1 MB   | Basic   | ext4?      | -                        |
| 8         | J:           | 2 MB   | Basic   | ext4?      | -                        |

## Windows Visibility

**Status**: Drive detected, partitions assigned letters, but **filesystems not readable**

- Windows assigns drive letters (E, G, H, I, J, K)
- All partitions show as 0 bytes (unrecognized filesystem)
- Filesystems are likely ext4 (Linux) from NAS OS

## Access Options

### Option 1: WSL Mount (Recommended)

- **Requirement**: Admin elevation
- **Command**: `wsl --mount --bare \\.\PHYSICALDRIVE2`
- **Benefit**: Full Linux filesystem support, native ext4 reading
- **Status**: Requires Claude Code restart as administrator

### Option 2: Third-Party Tools

Install Windows ext4 reader:

- **DiskInternals Linux Reader** (free)
- **Ext2Fsd** (open source)
- **Linux File Systems for Windows by Paragon** (paid)

### Option 3: Python ext4 Library

- Use `python-ext4` or similar to read raw disk
- More complex, requires low-level disk access
- Good for automation but slower development

## Access Status (2026-03-05)

### WSL Mount - FAILED ❌

- **Issue**: Hyper-V virtualization layer errors (hv_storvsc SCSI failures)
- **Status**: WSL cannot reliably access the physical drive through virtualization
- **Resolution**: Using DiskInternals Linux Reader instead

### DiskInternals Linux Reader - SUCCESS ✅

- **Status**: Working after application restart
- **Access**: Full read access to 3.7TB partition
- **Folders**: Can navigate through familiar folder structure
- **Resolution**: Initial hang was transient, second launch succeeded

## Diagnosis

**WSL Mount**: Failed due to Hyper-V virtualization layer errors
**DiskInternals**: Succeeded on second attempt - likely initial detection issue from hot-swap
**SMART Status**: Drive is physically healthy (OK status, Serial: WD-WCC4E7KFC7F4)
**Filesystem**: ext4 filesystem is intact and fully readable

## Next Steps

### 1. Identify Access Path

Determine how to access the partition programmatically:
- Check if DiskInternals assigns a virtual drive letter
- Or use DiskInternals export/save functionality
- Or mount with Ext2Fsd for command-line access

### 2. Run Initial Scan

Once path is identified:
- Use `scan_g_drive.py` to catalog all files
- Record file sizes, paths, and metadata
- Store results in `output/archive.db`

### 3. Analyze Contents

- Generate file listing report
- Size analysis by folder
- Duplicate detection across all drives

## NAS Context

**Original NAS Setup**: Z: drive (network)

**Physical Extraction**: Removed multiple drives from NAS enclosure

- **4TB WD Red** (this drive) - Currently connected via SATA
- **1TB Blue** - Available
- **2TB Black** - Available

**Note**: The original W: drive reference in documentation referred to another NAS drive that has been physically removed and disassembled.

## Technical Notes

- NAS drives typically use ext4 for better Linux compatibility
- 8 partitions suggest complex NAS OS setup (boot, swap, system, data, config)
- Main data partition (K:) is 3.7TB - this is our primary target
- Other partitions likely contain NAS OS, logs, config databases
