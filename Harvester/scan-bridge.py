#!/usr/bin/env python3
"""
Bridge scanner: catalog a folder-level backup (not a whole physical disk) from WSL.

Runs python/scan_drive_win.py's own walk, skip rules and SHA-256 hashing unchanged, so a
folder backup is catalogued exactly the way every docked drive has been. Only the drive
identity differs: scan_drive_win.py asks PowerShell for the physical disk, which agents on
this box may not run and which would describe the dock disk rather than the backup. Here
the identity is a BRIDGE-<code> record, the convention harvest-nasr.py set for NASR.

Usage:
    python3 Harvester/scan-bridge.py /mnt/w/X1-backup --drive-code X1BK \
        --label "X1 laptop C:\\Users robocopy, 2026-09-29" \
        --model "robocopy of the Lenovo X1 C:\\Users (W:\\X1-backup)"

Output: Harvester/manifests/scan-<code>-<date>.jsonl (feed to python/import_scan.py).
Never writes to the source.
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "python"))
import scan_drive_win  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Catalog a folder backup with the archive's scanner")
    ap.add_argument("root", help="the backup folder, as a WSL path (e.g. /mnt/w/X1-backup)")
    ap.add_argument("--drive-code", required=True)
    ap.add_argument("--label", required=True, help="human label for the drive record")
    ap.add_argument("--model", required=True, help="what this backup is, for the drive record")
    ap.add_argument("--no-hash", action="store_true", help="catalog only (default hashes every file >= 1 KB)")
    args = ap.parse_args()

    if not os.path.isdir(args.root):
        print(f"ERROR: {args.root} is not an accessible folder", file=sys.stderr)
        return 1

    size = 0  # a folder has no disk size; the summary record carries the bytes scanned

    def bridge_identity(_drive_path: str) -> dict:
        return {
            "serial_number": f"BRIDGE-{args.drive_code}",
            "model": args.model,
            "size_bytes": size,
            "manufacturer": None,
            "firmware_version": None,
            "media_type": "folder backup",
            "bus_type": "USB",
            "filesystem": "NTFS",
            "volume_label": args.label,
            "connection_method": "USB dock",
        }

    scan_drive_win.get_drive_identity = bridge_identity
    out = REPO / "Harvester" / "manifests" / f"scan-{args.drive_code}-{datetime.now():%Y%m%d}.jsonl"
    argv = [args.root, "--drive-code", args.drive_code, "--drive-label", args.label,
            "--output", str(out), "--no-progress"]
    if not args.no_hash:
        argv.append("--hash")
    sys.argv = ["scan_drive_win.py", *argv]
    rc = scan_drive_win.main()
    if rc == 0:
        fix_scan_source(out, args.root)
    return rc


def fix_scan_source(out: Path, root: str) -> None:
    """scan_drive_win.py writes the drive letter's first character ("/:\\" for a WSL path);
    record the backup folder as Windows sees it (/mnt/w/X1-backup -> W:\\X1-backup)."""
    import json
    parts = Path(root).parts  # ('/', 'mnt', 'w', 'X1-backup')
    win = f"{parts[2].upper()}:\\" + "\\".join(parts[3:]) if len(parts) > 2 and parts[1] == "mnt" else root
    tmp = out.with_suffix(".tmp")
    with open(out, encoding="utf-8") as src, open(tmp, "w", encoding="utf-8") as dst:
        first = json.loads(src.readline())
        first["scan_source"] = win
        dst.write(json.dumps(first) + "\n")
        for line in src:
            dst.write(line)
    os.replace(tmp, out)


if __name__ == "__main__":
    sys.exit(main())
