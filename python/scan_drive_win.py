#!/usr/bin/env python3
"""
Windows-native drive scanner — outputs JSONL for WSL import

This script is designed to run from Windows Python (not WSL) to scan drives
that have NTFS ACLs blocking WSL access (e.g. Users/steve/ on Windows boot
drives). It outputs a JSONL file that can be imported into archive.db from
WSL using import_scan.py.

Usage (from Windows cmd/PowerShell):
    python scan_drive_win.py H:\\
    python scan_drive_win.py H:\\ --drive-code POCL --hash
    python scan_drive_win.py C:\\ --drive-code CDRV --hash --output scan-CDRV.jsonl

The JSONL output contains three record types:
    {"type": "drive", ...}   — one drive identity record (first line)
    {"type": "file", ...}    — one per scanned file
    {"type": "summary", ...} — final summary record (last line)

Requirements: Python 3.10+ stdlib only. tqdm is optional (progress bar).
"""

import os
import sys
import json
import time
import hashlib
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

# Optional tqdm for progress bar
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Directories to always skip
ALWAYS_SKIP_DIRS = {
    '$recycle.bin', 'system volume information', '$windows.~bt',
    'windows.old', '.trash', 'config.msi', 'recovery', '$winreagent',
}

# Windows boot directories to skip (top-level only, when --windows-boot)
WINDOWS_BOOT_DIRS = {
    'windows', 'program files', 'program files (x86)',
}

# Smart subdirectory skips (cache, temp, dev artifacts)
SMART_SKIP_DIRS = {
    'cache', 'temp', 'tmp', 'logs',
    'node_modules', '__pycache__', '.git', '.svn',
    'venv', '.venv',
}

# System files to skip
SYSTEM_FILES = {
    'pagefile.sys', 'hiberfil.sys', 'swapfile.sys',
    'bootmgr', 'bootnxt', 'bootsect.bak', '$upg$pbr.marker',
}

HASH_CHUNK_SIZE = 65536  # 64 KB read buffer for SHA-256
MIN_HASH_SIZE = 1024     # Only hash files >= 1 KB


# ---------------------------------------------------------------------------
# Drive identity via PowerShell
# ---------------------------------------------------------------------------

def get_drive_identity(drive_path: str) -> dict:
    """
    Get physical drive identity using PowerShell Get-PhysicalDisk.

    Args:
        drive_path: Windows drive path like "H:\\"

    Returns:
        Dict with serial_number, model, size_bytes, media_type, bus_type, etc.
    """
    drive_letter = drive_path[0].upper()

    ps_script = f"""
$ErrorActionPreference = 'SilentlyContinue'
$part = Get-Partition -DriveLetter {drive_letter}
if ($part) {{
    $disk = Get-PhysicalDisk -DeviceNumber $part.DiskNumber
    $wmi  = Get-WmiObject Win32_DiskDrive | Where-Object {{ $_.Index -eq $part.DiskNumber }}
    $vol  = Get-Volume -DriveLetter {drive_letter}
    @{{
        SerialNumber    = ($disk.SerialNumber -replace '\\s+$','')
        Model           = ($disk.Model -replace '\\s+$','')
        MediaType       = $disk.MediaType
        BusType         = $disk.BusType
        Manufacturer    = $disk.Manufacturer
        FirmwareVersion = $disk.FirmwareVersion
        SizeBytes       = [long]$disk.Size
        WmiSerial       = ($wmi.SerialNumber -replace '\\s+$','')
        WmiModel        = ($wmi.Model -replace '\\s+$','')
        InterfaceType   = $wmi.InterfaceType
        Filesystem      = $vol.FileSystemType
        VolumeLabel     = $vol.FileSystemLabel
        DiskNumber      = $part.DiskNumber
    }} | ConvertTo-Json
}} else {{
    @{{ Error = "No partition found for drive letter {drive_letter}" }} | ConvertTo-Json
}}
"""

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            if "Error" in data:
                print(f"WARNING: {data['Error']}", file=sys.stderr)
                return _fallback_identity(drive_path)

            serial = (data.get("SerialNumber") or data.get("WmiSerial") or "").strip()
            model = (data.get("Model") or data.get("WmiModel") or "Unknown").strip()

            return {
                "serial_number": serial if serial else f"UNKNOWN_{drive_letter}",
                "model": model,
                "manufacturer": (data.get("Manufacturer") or "").strip() or None,
                "firmware_version": (data.get("FirmwareVersion") or "").strip() or None,
                "size_bytes": int(data.get("SizeBytes") or 0),
                "media_type": data.get("MediaType") or None,
                "bus_type": data.get("BusType") or None,
                "interface_type": data.get("InterfaceType") or None,
                "filesystem": data.get("Filesystem") or None,
                "volume_label": data.get("VolumeLabel") or None,
                "connection_method": (
                    "Direct" if data.get("BusType") in ("SATA", "NVMe", "IDE")
                    else "USB/Bridge"
                ),
            }
        else:
            print(f"WARNING: PowerShell returned no output: {result.stderr.strip()}", file=sys.stderr)
            return _fallback_identity(drive_path)

    except subprocess.TimeoutExpired:
        print("WARNING: PowerShell timed out querying drive identity", file=sys.stderr)
        return _fallback_identity(drive_path)
    except Exception as e:
        print(f"WARNING: Drive identity query failed: {e}", file=sys.stderr)
        return _fallback_identity(drive_path)


def _fallback_identity(drive_path: str) -> dict:
    """Fallback when PowerShell identity fails."""
    letter = drive_path[0].upper()
    return {
        "serial_number": f"UNKNOWN_{letter}",
        "model": f"Unknown Drive {letter}:",
        "manufacturer": None,
        "firmware_version": None,
        "size_bytes": 0,
        "media_type": None,
        "bus_type": None,
        "interface_type": None,
        "filesystem": None,
        "volume_label": None,
        "connection_method": "Unknown",
    }


# ---------------------------------------------------------------------------
# File scanning
# ---------------------------------------------------------------------------

def should_skip_dir(dirname: str, is_top_level: bool, windows_boot: bool) -> bool:
    """Decide whether to prune a directory."""
    lower = dirname.lower()
    if lower in ALWAYS_SKIP_DIRS:
        return True
    if windows_boot and is_top_level and lower in WINDOWS_BOOT_DIRS:
        return True
    if lower in SMART_SKIP_DIRS:
        return True
    return False


def should_skip_file(filename: str) -> bool:
    """Decide whether to skip a system file."""
    return filename.lower() in SYSTEM_FILES


def compute_sha256(filepath: str) -> str | None:
    """Compute SHA-256 of a file, returning hex digest or None on error."""
    try:
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(HASH_CHUNK_SIZE)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    except (PermissionError, OSError):
        return None


def count_files(drive_root: str, windows_boot: bool) -> int:
    """Quick count of files for progress bar sizing."""
    count = 0
    drive_root_path = Path(drive_root)
    for root, dirs, files in os.walk(drive_root):
        is_top = Path(root) == drive_root_path
        dirs[:] = [d for d in dirs if not should_skip_dir(d, is_top, windows_boot)]
        count += len([f for f in files if not should_skip_file(f)])
    return count


def is_hidden_or_system(filepath: str):
    """Check Windows hidden/system attributes via file attributes."""
    try:
        import ctypes
        attrs = ctypes.windll.kernel32.GetFileAttributesW(filepath)
        if attrs == -1:
            return False, False
        hidden = bool(attrs & 0x2)
        system = bool(attrs & 0x4)
        return hidden, system
    except Exception:
        # Non-Windows or ctypes unavailable — fall back to name heuristic
        return os.path.basename(filepath).startswith('.'), False


def scan_files(drive_root: str, windows_boot: bool, enable_hash: bool,
               show_progress: bool):
    """
    Generator that yields file info dicts for every file on the drive.

    Args:
        drive_root: Root path (e.g. "H:\\")
        windows_boot: If True, skip Windows/Program Files at top level
        enable_hash: Compute SHA-256 for files >= MIN_HASH_SIZE
        show_progress: Show tqdm progress bar (requires tqdm)

    Yields:
        dict with keys: path, size_bytes, modified_date, created_date,
        extension, hash, is_hidden, is_system
    """
    drive_root_path = Path(drive_root)
    total = None
    pbar = None

    if show_progress:
        if HAS_TQDM:
            print("Counting files...", file=sys.stderr)
            total = count_files(drive_root, windows_boot)
            print(f"Found {total:,} files to scan", file=sys.stderr)
            pbar = tqdm(total=total, unit=" files", desc="Scanning",
                        file=sys.stderr)
        else:
            print("(tqdm not installed — no progress bar)", file=sys.stderr)

    for root, dirs, files in os.walk(drive_root):
        root_path = Path(root)
        is_top = root_path == drive_root_path

        # Prune directories in place
        dirs[:] = [d for d in dirs if not should_skip_dir(d, is_top, windows_boot)]

        for fname in files:
            if should_skip_file(fname):
                if pbar:
                    pbar.update(1)
                continue

            filepath = os.path.join(root, fname)

            try:
                stat = os.stat(filepath)
            except (PermissionError, OSError):
                if pbar:
                    pbar.update(1)
                yield None  # signal error
                continue

            # Relative path using forward slashes
            try:
                rel_path = str(Path(filepath).relative_to(drive_root_path))
            except ValueError:
                rel_path = filepath
            rel_path = rel_path.replace("\\", "/")

            size = stat.st_size
            ext = Path(fname).suffix.lower()

            # Dates as ISO strings
            modified = datetime.fromtimestamp(stat.st_mtime).isoformat()
            created = datetime.fromtimestamp(stat.st_ctime).isoformat()

            # Hash
            file_hash = None
            if enable_hash and size >= MIN_HASH_SIZE:
                file_hash = compute_sha256(filepath)

            is_hidden, is_system = is_hidden_or_system(filepath)

            if pbar:
                pbar.update(1)

            yield {
                "path": rel_path,
                "size_bytes": size,
                "modified_date": modified,
                "created_date": created,
                "extension": ext,
                "hash": f"sha256:{file_hash}" if file_hash else None,
                "is_hidden": is_hidden,
                "is_system": is_system,
            }

    if pbar:
        pbar.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Windows-native drive scanner — outputs JSONL for WSL import"
    )
    parser.add_argument(
        "drive_path",
        help="Windows drive path to scan (e.g. H:\\)",
    )
    parser.add_argument(
        "--drive-code",
        help="Short drive code tag (e.g. POCL)",
    )
    parser.add_argument(
        "--drive-label",
        help="Human-readable label for this drive",
    )
    parser.add_argument(
        "--hash",
        action="store_true",
        help="Compute SHA-256 hash for each file >= 1 KB",
    )
    parser.add_argument(
        "--windows-boot",
        action="store_true",
        help="Skip Windows/Program Files at drive root",
    )
    parser.add_argument(
        "--output", "-o",
        help="JSONL output path (default: scan-<code>-<date>.jsonl in cwd)",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable progress bar",
    )

    args = parser.parse_args()

    drive_path = args.drive_path
    # Normalize: ensure trailing backslash for root paths
    if len(drive_path) == 2 and drive_path[1] == ":":
        drive_path += "\\"

    if not os.path.isdir(drive_path):
        print(f"ERROR: {drive_path} is not an accessible directory", file=sys.stderr)
        return 1

    # Determine output path
    code = args.drive_code or drive_path[0].upper()
    date_str = datetime.now().strftime("%Y%m%d")
    output_path = args.output or f"scan-{code}-{date_str}.jsonl"

    print(f"Scanning {drive_path}", file=sys.stderr)
    print(f"Drive code: {code}", file=sys.stderr)
    print(f"Hashing: {'yes' if args.hash else 'no'}", file=sys.stderr)
    print(f"Output: {output_path}", file=sys.stderr)
    print(file=sys.stderr)

    # --- Drive identity ---
    print("Querying drive identity...", file=sys.stderr)
    identity = get_drive_identity(drive_path)
    print(f"  Model: {identity['model']}", file=sys.stderr)
    print(f"  Serial: {identity['serial_number']}", file=sys.stderr)
    print(f"  Size: {identity['size_bytes'] / (1024**3):.1f} GB", file=sys.stderr)
    print(file=sys.stderr)

    # Build drive record
    drive_record = {
        "type": "drive",
        "serial_number": identity["serial_number"],
        "model": identity["model"],
        "size_bytes": identity["size_bytes"],
        "manufacturer": identity.get("manufacturer"),
        "firmware_version": identity.get("firmware_version"),
        "media_type": identity.get("media_type"),
        "bus_type": identity.get("bus_type"),
        "filesystem": identity.get("filesystem"),
        "volume_label": identity.get("volume_label"),
        "connection_method": identity.get("connection_method"),
        "drive_code": args.drive_code,
        "drive_label": args.drive_label,
        "scan_source": f"{drive_path[0].upper()}:\\",
        "scanned_at": datetime.now().isoformat(),
    }

    # --- File scan ---
    start_time = time.time()
    total_files = 0
    total_size = 0
    error_count = 0

    with open(output_path, "w", encoding="utf-8") as out:
        # Write drive record first
        out.write(json.dumps(drive_record, ensure_ascii=False) + "\n")

        for file_info in scan_files(
            drive_path,
            windows_boot=args.windows_boot,
            enable_hash=args.hash,
            show_progress=not args.no_progress,
        ):
            if file_info is None:
                error_count += 1
                continue

            record = {"type": "file", **file_info}
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            total_files += 1
            total_size += file_info["size_bytes"]

        # Write summary
        duration = time.time() - start_time
        summary = {
            "type": "summary",
            "total_files": total_files,
            "total_size_bytes": total_size,
            "errors": error_count,
            "scan_duration_secs": round(duration, 1),
            "hashing_enabled": args.hash,
            "completed_at": datetime.now().isoformat(),
        }
        out.write(json.dumps(summary, ensure_ascii=False) + "\n")

    # Print final report to stderr
    print(file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print("SCAN COMPLETE", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print(f"  Files:    {total_files:,}", file=sys.stderr)
    print(f"  Size:     {total_size / (1024**3):.2f} GB", file=sys.stderr)
    print(f"  Errors:   {error_count}", file=sys.stderr)
    print(f"  Duration: {duration:.0f}s", file=sys.stderr)
    print(f"  Output:   {output_path}", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
