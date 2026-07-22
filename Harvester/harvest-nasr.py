#!/usr/bin/env python3
"""
NASR harvester — stage the ddrescue'd QNAP-NAS tree (OldNAS) from the read-only
dock to the MasterArchive, in a single read pass that also produces the catalog.

Context (bead da-yc6): NASR is the 2TB Sabrent-dock drive holding the file-by-file
ddrescue of the dead QNAP NAS's degraded disk (bead da-xy2). It is docked as
M: "NASRed" and is STRICTLY READ-ONLY. This tool never writes to M:.

One walk over M:\\OldNAS does everything:
  * classify each file (content / firmware-artifact / zero-byte / rescue-meta)
  * copy CONTENT to Z:\\Harvest\\NASR\\OldNAS\\ while streaming a sha256
  * emit the harvest manifest (src/size/hash/action/dst) — a complete ledger of
    every file on the drive and its disposition
  * emit an import_scan.py-compatible catalog JSONL (drive/file/summary) for the
    CONTENT files, each carrying its sha256

Skip conventions follow Harvester/copy-nas-to-dock.sh is_skippable():
  .wdmc/ .wdphotos/ .groupingDb/  Folder.jpg  AlbumArt_*.jpg  -> firmware artifact
Plus:
  0-byte files                                                -> zero
  .rescue-logs/ .rescue-maps/  (ddrescue bookkeeping, not NAS content) -> rescue-meta

Firmware-artifact, zero, and rescue-meta files are RECORDED in the manifest (with
size) but NOT copied and NOT cataloged — the archive holds history, not firmware
thumbnails or rescue bookkeeping. Content files are copied, hashed, and cataloged.

Resumable: a content file whose destination already exists with a matching size is
not re-copied; its sha256 is recomputed from the (local) destination instead.

Usage:
    python3 Harvester/harvest-nasr.py [--limit N] [--dry-run]

Outputs:
    Harvester/manifests/harvest-NASR.jsonl          (harvest ledger)
    Harvester/manifests/scan-NASR-<date>.jsonl      (catalog, feed to import_scan.py)
    data/logs/harvest-nasr-<date>.log               (tee'd by the caller)
"""

import os
import sys
import json
import time
import hashlib
import argparse
import shutil
from pathlib import Path
from datetime import datetime

SRC_ROOT   = "/mnt/m/OldNAS"
DST_ROOT   = "/mnt/z/Harvest/NASR/OldNAS"
SRC_WIN    = "M:\\OldNAS"
DST_WIN    = "Z:\\Harvest\\NASR\\OldNAS"

DRIVE_CODE = "NASR"
REPO       = Path(__file__).resolve().parent.parent           # /root/projects/DataArchive
MANIFEST   = REPO / "Harvester" / "manifests" / "harvest-NASR.jsonl"
SCAN_JSONL = REPO / "Harvester" / "manifests" / f"scan-NASR-{datetime.now():%Y%m%d}.jsonl"

ARTIFACT_DIRS   = {".wdmc", ".wdphotos", ".groupingDb"}
RESCUE_META     = {".rescue-logs", ".rescue-maps"}
CHUNK           = 8 * 1024 * 1024


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def classify(rel_parts, name, size):
    """rel_parts = directory components under OldNAS; name = filename."""
    for p in rel_parts:
        if p in RESCUE_META:
            return "rescue-meta"
    for p in rel_parts:
        if p in ARTIFACT_DIRS:
            return "artifact"
    if name == "Folder.jpg":
        return "artifact"
    if name.startswith("AlbumArt_") and name.lower().endswith(".jpg"):
        return "artifact"
    if size == 0:
        return "zero"
    return "content"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_and_hash(src, dst):
    """Stream src -> dst computing sha256 in the same pass. Returns hex digest."""
    h = hashlib.sha256()
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".partial"
    with open(src, "rb") as fi, open(tmp, "wb") as fo:
        for chunk in iter(lambda: fi.read(CHUNK), b""):
            h.update(chunk)
            fo.write(chunk)
    os.replace(tmp, dst)
    shutil.copystat(src, dst, follow_symlinks=False)
    return h.hexdigest()


def iter_files():
    for dirpath, dirnames, filenames in os.walk(SRC_ROOT):
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, SRC_ROOT)
            yield full, rel, name


def main():
    ap = argparse.ArgumentParser(description="Harvest NASR OldNAS tree to MasterArchive")
    ap.add_argument("--limit", type=int, default=0, help="stop after N files (testing)")
    ap.add_argument("--dry-run", action="store_true", help="classify + count only; no copy, no hash, no output files")
    args = ap.parse_args()

    if not os.path.isdir(SRC_ROOT):
        log(f"FATAL: source {SRC_ROOT} not present — is NASR (M:) docked/mounted?")
        return 2

    log(f"NASR harvest starting. src={SRC_ROOT} (read-only)  dst={DST_ROOT}")
    counts = {"content": 0, "artifact": 0, "zero": 0, "rescue-meta": 0, "error": 0, "resumed": 0}
    bytes_copied = 0
    bytes_content = 0
    t0 = time.time()

    mf = None if args.dry_run else open(MANIFEST, "w", encoding="utf-8")
    sf = None if args.dry_run else open(SCAN_JSONL, "w", encoding="utf-8")

    # Drive record first line of the catalog JSONL.
    if sf:
        drive_rec = {
            "type": "drive",
            "serial_number": "BRIDGE-NASR",
            "model": "ddrescue image of dead QNAP NAS disk (2TB Sabrent dock)",
            "manufacturer": "QNAP (recovered)",
            "size_bytes": 2000382062592,
            "filesystem": "NTFS",
            "drive_label": "NASRed",
            "connection_method": "USB",
            "media_type": "HDD",
            "bus_type": "USB",
            "drive_code": DRIVE_CODE,
            "scan_source": SRC_WIN,
        }
        sf.write(json.dumps(drive_rec) + "\n")

    n = 0
    for full, rel, name in iter_files():
        n += 1
        if args.limit and n > args.limit:
            n -= 1
            break
        rel_parts = rel.split(os.sep)[:-1]
        try:
            st = os.stat(full)
        except OSError as e:
            counts["error"] += 1
            log(f"  STAT ERROR {rel}: {e}")
            continue
        size = st.st_size
        kind = classify(rel_parts, name, size)
        rel_fwd = rel.replace(os.sep, "/")
        rel_bs = rel.replace(os.sep, "\\")
        src_win = f"{SRC_WIN}\\{rel_bs}"

        if kind == "content":
            dst = os.path.join(DST_ROOT, rel)
            dst_win = f"{DST_WIN}\\{rel_bs}"
            if args.dry_run:
                digest = None
            else:
                try:
                    if os.path.exists(dst) and os.path.getsize(dst) == size:
                        digest = sha256_file(dst)          # resume: hash local copy
                        counts["resumed"] += 1
                    else:
                        digest = copy_and_hash(full, dst)
                        bytes_copied += size
                except OSError as e:
                    counts["error"] += 1
                    log(f"  COPY ERROR {rel}: {e}")
                    continue
            counts["content"] += 1
            bytes_content += size
            if mf:
                mf.write(json.dumps({"src": src_win, "size": size, "hash": digest,
                                     "action": "copy", "dst": dst_win}) + "\n")
            if sf:
                ext = os.path.splitext(name)[1].lower()
                sf.write(json.dumps({
                    "type": "file", "path": rel_fwd, "size_bytes": size,
                    "modified_date": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "created_date": datetime.fromtimestamp(st.st_ctime).isoformat(sep=" "),
                    "extension": ext,
                    "is_hidden": name.startswith("."),
                    "is_system": False,
                    "hash": "sha256:" + digest if digest else None,
                }) + "\n")
        else:
            counts[kind] += 1
            action = {"artifact": "skip:artifact", "zero": "skip:zero",
                      "rescue-meta": "skip:rescue-meta"}[kind]
            if mf:
                mf.write(json.dumps({"src": src_win, "size": size,
                                     "action": action, "dst": None}) + "\n")

        if n % 500 == 0:
            rate = bytes_copied / (time.time() - t0 + 1e-9) / 1e6
            log(f"  {n:,} files | content={counts['content']:,} "
                f"copied={bytes_copied/1e9:.1f}GB resumed={counts['resumed']:,} "
                f"artifact={counts['artifact']:,} zero={counts['zero']} "
                f"@ {rate:.0f}MB/s")

    elapsed = time.time() - t0
    if sf:
        sf.write(json.dumps({"type": "summary", "total_files": counts["content"],
                             "errors": counts["error"],
                             "scan_duration_secs": round(elapsed, 1)}) + "\n")
    if mf: mf.close()
    if sf: sf.close()

    log("=" * 64)
    log(f"HARVEST {'DRY-RUN ' if args.dry_run else ''}COMPLETE  ({elapsed/60:.1f} min)")
    log(f"  walked        : {n:,} files")
    log(f"  content copied: {counts['content']:,} files, {bytes_content/1e9:.1f} GB")
    log(f"  (bytes newly copied this run: {bytes_copied/1e9:.1f} GB; resumed/rehashed: {counts['resumed']:,})")
    log(f"  skip:artifact : {counts['artifact']:,}")
    log(f"  skip:zero     : {counts['zero']}")
    log(f"  skip:rescue   : {counts['rescue-meta']}")
    log(f"  errors        : {counts['error']}")
    if not args.dry_run:
        log(f"  manifest : {MANIFEST}")
        log(f"  catalog  : {SCAN_JSONL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
