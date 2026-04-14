#!/usr/bin/env python3
"""
Harvest Plan Generator — Stage 1 of the harvest engine.

Queries archive.db for files on a scanned drive, applies inclusion/exclusion
filters and cross-drive deduplication, outputs a JSONL manifest for the
PowerShell executor.

Usage:
    python harvest_plan.py --config /mnt/c/Users/steve/OneDrive/Tools/DataArchiver/configs/WWYY.json
    python harvest_plan.py --config /mnt/c/Users/steve/OneDrive/Tools/DataArchiver/configs/Tera1A.json
"""

import sys
import json
import sqlite3
import argparse
import fnmatch
from pathlib import Path
from collections import defaultdict

HARVESTER_ROOT_WSL = Path("/mnt/c/Users/steve/OneDrive/Tools/DataArchiver")
HARVESTER_ROOT_WIN = r"C:\Users\steve\OneDrive\Tools\DataArchiver"
DB_PATH = "data/archive.db"

DEFAULT_EXCLUDE_EXT = {
    '.exe', '.dll', '.msi', '.msp', '.ocx', '.sys', '.drv',
    '.com', '.scr', '.cpl', '.iso', '.cab', '.cat'
}

DEFAULT_EXCLUDE_PATHS = [
    'Boot', '$RECYCLE.BIN', 'System Volume Information', 'Windows',
    'ProgramData', 'Program Files', 'Program Files (x86)',
    'Recovery', 'PerfLogs', 'Config.Msi'
]


def load_config(config_path):
    with open(config_path) as f:
        return json.load(f)


def load_claimed_hashes(progress_dir):
    """Load hashes already claimed by prior harvests."""
    claimed = {}  # hash -> destination path
    progress_dir = Path(progress_dir)
    if not progress_dir.exists():
        return claimed

    for pf in progress_dir.glob("harvest-*.progress.jsonl"):
        with open(pf) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if rec.get("status") == "done" and rec.get("hash"):
                        claimed[rec["hash"]] = rec.get("dst", rec.get("src", ""))
                except json.JSONDecodeError:
                    continue
    return claimed


def normalize_path(p):
    """Normalize separators to forward slash for matching."""
    return p.replace('\\', '/')


def path_matches_include(path, includes):
    """Check if a normalized path matches any include rule."""
    parts = path.split('/')
    top = parts[0] if parts else ''

    for inc in includes:
        inc = normalize_path(inc)

        # Exact top-level folder match: "Code" matches "Code/anything"
        if '/' not in inc and '*' not in inc:
            if top.lower() == inc.lower():
                return True

        # Subfolder match: "Backups/restore" matches "Backups/restore/anything"
        elif '*' not in inc:
            if path.lower().startswith(inc.lower() + '/') or path.lower() == inc.lower():
                return True

        # Glob pattern: "Downloads/*.pdf"
        else:
            if fnmatch.fnmatch(path.lower(), inc.lower()):
                return True

    return False


def path_matches_exclude(path, excludes):
    """Check if a normalized path starts with any excluded prefix."""
    parts = path.split('/')
    top = parts[0] if parts else ''
    for exc in excludes:
        if top.lower() == normalize_path(exc).lower():
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description='Generate harvest manifest')
    parser.add_argument('--config', required=True, help='Path to drive config JSON')
    parser.add_argument('--db', default=DB_PATH, help='Database path')
    parser.add_argument('--staging', default='W:', help='Staging drive letter')
    args = parser.parse_args()

    config = load_config(args.config)
    label = config['label']
    drive_letter = config['drive_letter']
    scan_id = config.get('scan_id')

    includes = config.get('include', [])
    include_root_ext = set(e.lower() for e in config.get('include_root_ext', []))
    exclude_ext = set(e.lower() for e in config.get('exclude_ext', list(DEFAULT_EXCLUDE_EXT)))
    exclude_paths = config.get('exclude_paths', DEFAULT_EXCLUDE_PATHS)

    staging_root = f"{args.staging}\\{label}"

    # Find scan_id if not specified
    db = sqlite3.connect(args.db)
    if not scan_id:
        row = db.execute("""
            SELECT s.scan_id FROM scans s
            JOIN drives d ON s.drive_id = d.drive_id
            WHERE d.label = ? OR d.drive_code = ?
            ORDER BY s.scan_id DESC LIMIT 1
        """, (label, label)).fetchone()
        if not row:
            print(f"ERROR: No scan found for {label}")
            sys.exit(1)
        scan_id = row[0]

    print(f"Generating manifest for {label} (scan {scan_id})")

    # Load claimed hashes from prior harvests
    progress_dir = HARVESTER_ROOT_WSL / "progress"
    claimed = load_claimed_hashes(progress_dir)
    print(f"  {len(claimed)} hashes claimed by prior harvests")

    # Load file hashes for this scan
    file_hashes = {}
    for file_id, hash_value in db.execute(
        "SELECT file_id, hash_value FROM file_hashes WHERE scan_id = ? AND hash_type = 'sha256'",
        (scan_id,)
    ):
        file_hashes[file_id] = hash_value

    print(f"  {len(file_hashes)} files have hashes")

    # Query all files
    files = db.execute(
        "SELECT file_id, path, size_bytes, extension FROM files WHERE scan_id = ?",
        (scan_id,)
    ).fetchall()

    print(f"  {len(files)} total files in scan")

    # Build manifest
    manifest_path = HARVESTER_ROOT_WSL / "manifests" / f"harvest-{label}.jsonl"
    stats = defaultdict(int)
    stats['total_copy_bytes'] = 0

    with open(manifest_path, 'w') as mf:
        for file_id, path, size_bytes, ext in files:
            norm_path = normalize_path(path)
            ext_lower = (ext or '').lower()

            # Build record
            src = f"{drive_letter}:\\{path.replace('/', chr(92))}"
            rec = {"src": src, "size": size_bytes or 0}

            # Check hash
            h = file_hashes.get(file_id)
            if h:
                rec["hash"] = h

            # --- Filters ---

            # Zero-byte
            if not size_bytes or size_bytes == 0:
                rec["action"] = "skip:zero"
                rec["dst"] = None
                stats['skip:zero'] += 1
                mf.write(json.dumps(rec) + '\n')
                continue

            # Excluded extension
            if ext_lower in exclude_ext:
                rec["action"] = "skip:ext"
                rec["dst"] = None
                stats['skip:ext'] += 1
                mf.write(json.dumps(rec) + '\n')
                continue

            # Inclusion logic
            if includes:
                # Check root-level extension includes
                is_root_file = '/' not in norm_path and '\\' not in path
                root_ext_match = is_root_file and ext_lower in include_root_ext

                if not root_ext_match and not path_matches_include(norm_path, includes):
                    rec["action"] = "skip:path"
                    rec["dst"] = None
                    stats['skip:path'] += 1
                    mf.write(json.dumps(rec) + '\n')
                    continue
            else:
                # No include list — use exclude paths
                if path_matches_exclude(norm_path, exclude_paths):
                    rec["action"] = "skip:path"
                    rec["dst"] = None
                    stats['skip:path'] += 1
                    mf.write(json.dumps(rec) + '\n')
                    continue

            # Dedup
            if h and h in claimed:
                rec["action"] = "skip:dupe"
                rec["dst"] = None
                rec["dupe_of"] = claimed[h]
                stats['skip:dupe'] += 1
                mf.write(json.dumps(rec) + '\n')
                continue

            # ── Copy ──
            dst_path = f"{staging_root}\\{path.replace('/', chr(92))}"
            rec["action"] = "copy"
            rec["dst"] = dst_path
            stats['copy'] += 1
            stats['total_copy_bytes'] += size_bytes or 0

            # Claim the hash
            if h:
                claimed[h] = dst_path

            mf.write(json.dumps(rec) + '\n')

    db.close()

    # Summary
    print(f"\nManifest: {manifest_path}")
    print(f"  Windows: {HARVESTER_ROOT_WIN}\\manifests\\harvest-{label}.jsonl")
    print(f"\nSummary:")
    print(f"  Copy:       {stats['copy']:>8} files  ({stats['total_copy_bytes']/1073741824:.1f} GB)")
    print(f"  Skip(ext):  {stats['skip:ext']:>8} files")
    print(f"  Skip(path): {stats['skip:path']:>8} files")
    print(f"  Skip(dupe): {stats['skip:dupe']:>8} files")
    print(f"  Skip(zero): {stats['skip:zero']:>8} files")
    total = sum(v for k, v in stats.items() if k != 'total_copy_bytes')
    print(f"  Total:      {total:>8} files")

    print(f"\n── Execute in elevated PowerShell: ──")
    print(f'Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass')
    print(f'& "{HARVESTER_ROOT_WIN}\\harvest-execute.ps1" -Manifest "{HARVESTER_ROOT_WIN}\\manifests\\harvest-{label}.jsonl"')


if __name__ == '__main__':
    main()
