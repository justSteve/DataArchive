#!/usr/bin/env python3
r"""
Harvest Executor (WSL variant) — Stage 2 of the harvest engine, WSL read path.

Functional twin of harvest-execute.ps1, but copies through the WSL 9p mounts
(/mnt/<letter>) instead of native Windows Copy-Item.

WHY THIS EXISTS
---------------
Drives that were live Windows installs with OneDrive Files-On-Demand store many
user files as cloud "placeholders" (reparse points). Native Windows Copy-Item
refuses these with "The file cannot be accessed by the system" when the owning
OneDrive account/provider is not mounted — which is always the case for an
abandoned drive. The WSL 9p file server, however, reads the locally-resident
bytes directly, so `cp` over /mnt/<letter> recovers the real content. This was
proven on drive SVNK (Samsung 830, 2026-07-21, da-89t): PowerShell copied 486 of
11,998 files (0 GB of real payload); WSL copied all of them byte-for-byte
(verified against the archive.db sha256 catalog).

Use this executor whenever harvest-execute.ps1 reports mass
"cannot be accessed by the system" errors. For ordinary drives either works.

CONTRACT (identical to harvest-execute.ps1)
-------------------------------------------
  - Reads a JSONL manifest produced by harvest_plan.py.
  - Copies every action=="copy" record from src -> dst.
  - Resumes: skips src already marked done in the progress file.
  - Verifies copied size == manifest size.
  - Appends one progress record per file to progress/<manifest-stem>.progress.jsonl
    ({"src","dst","status":"done|error","bytes"|"error", ["hash"]}).
  - Writes a human summary + error tail to progress/<manifest-stem>.log.

Windows drive paths in the manifest (K:\..., Z:\...) are translated to WSL mounts
(/mnt/k/..., /mnt/z/...). STRICTLY READ-ONLY on every source drive: this script
only reads src and only writes under dst.

Usage:
    python3 harvest-execute-wsl.py --manifest manifests/harvest-SVNK.jsonl
    python3 harvest-execute-wsl.py --manifest manifests/harvest-SVNK.jsonl --verify-hash
"""

import os
import sys
import json
import shutil
import hashlib
import argparse
from datetime import datetime
from pathlib import Path

HARVESTER_ROOT = Path(__file__).resolve().parent


def win_to_wsl(p: str) -> str:
    """Translate a Windows drive path (e.g. 'K:\\Users\\x') to a WSL mount
    path ('/mnt/k/Users/x'). Leaves already-POSIX paths untouched."""
    p = p.strip()
    if len(p) >= 2 and p[1] == ':' and p[0].isalpha():
        drive = p[0].lower()
        rest = p[2:].lstrip('\\/').replace('\\', '/')
        return f"/mnt/{drive}/{rest}"
    return p.replace('\\', '/')


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def load_completed(progress_file: Path) -> set:
    done = set()
    if not progress_file.exists():
        return done
    with open(progress_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if rec.get('status') == 'done':
                    done.add(rec['src'])
            except (json.JSONDecodeError, KeyError):
                continue
    return done


def main():
    ap = argparse.ArgumentParser(description='Harvest executor (WSL read path)')
    ap.add_argument('--manifest', required=True, help='Path to harvest-<LABEL>.jsonl')
    ap.add_argument('--verify-hash', action='store_true',
                    help='Also verify copied file sha256 against the manifest hash (slower)')
    ap.add_argument('--progress-every', type=int, default=200,
                    help='Emit a progress line every N processed files')
    args = ap.parse_args()

    manifest = Path(args.manifest)
    if not manifest.is_absolute():
        manifest = (Path.cwd() / manifest).resolve()
    if not manifest.exists():
        print(f"ERROR: manifest not found: {manifest}", file=sys.stderr)
        return 1

    progress_dir = HARVESTER_ROOT / 'progress'
    progress_dir.mkdir(exist_ok=True)
    stem = manifest.stem  # harvest-SVNK
    progress_file = progress_dir / f"{stem}.progress.jsonl"
    log_file = progress_dir / f"{stem}.log"

    start = datetime.now()
    print(f"Harvest (WSL) started: {start} | Manifest: {manifest}")
    with open(log_file, 'w', encoding='utf-8') as lf:
        lf.write(f"Harvest (WSL) started: {start} | Manifest: {manifest}\n")

    completed = load_completed(progress_file)
    if completed:
        print(f"Resume: {len(completed)} files already done, will skip")

    # Read manifest, collect copy actions
    to_copy = []
    total_entries = 0
    with open(manifest, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total_entries += 1
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get('action') == 'copy':
                to_copy.append(rec)

    pending = [r for r in to_copy if r['src'] not in completed]
    print(f"Manifest: {total_entries} entries, {len(to_copy)} to copy, "
          f"{len(to_copy) - len(pending)} already done, {len(pending)} pending")

    if not pending:
        print("Nothing to do - all files already copied.")
        return 0

    copied = errors = 0
    total_bytes = 0
    error_list = []

    with open(progress_file, 'a', encoding='utf-8') as pf:
        for i, rec in enumerate(pending, 1):
            src_win = rec['src']
            dst_win = rec['dst']
            expected = rec.get('size', 0)
            h = rec.get('hash')

            src = win_to_wsl(src_win)
            dst = win_to_wsl(dst_win)

            out = {'src': src_win, 'dst': dst_win}
            if h:
                out['hash'] = h
            try:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                # Clear any pre-existing destination (e.g. a read-only file left by
                # a prior harvest-execute.ps1 run) so the overwrite cannot fail with
                # EACCES. Only ever touches the destination, never the source.
                if os.path.lexists(dst):
                    try:
                        os.chmod(dst, 0o666)
                    except OSError:
                        pass
                    try:
                        os.remove(dst)
                    except OSError:
                        pass
                # copyfile: content only, never touches source. Source is read-only.
                shutil.copyfile(src, dst)
                actual = os.path.getsize(dst)
                if expected and actual != expected:
                    raise IOError(f"Size mismatch: expected {expected}, got {actual}")
                if args.verify_hash and h:
                    got = sha256_of(dst)
                    if got != h:
                        raise IOError(f"Hash mismatch: expected {h}, got {got}")
                out['status'] = 'done'
                out['bytes'] = actual
                copied += 1
                total_bytes += actual
            except Exception as e:
                out['status'] = 'error'
                out['error'] = str(e)
                errors += 1
                if len(error_list) < 50:
                    error_list.append(f"{src_win} : {e}")

            pf.write(json.dumps(out) + '\n')

            if i % args.progress_every == 0:
                pf.flush()
                pct = i / len(pending) * 100
                gb = total_bytes / 1073741824
                elapsed_min = (datetime.now() - start).total_seconds() / 60
                rate = copied / elapsed_min if elapsed_min > 0 else 0
                print(f"{pct:.1f}% | {copied} copied | {errors} errors | "
                      f"{gb:.2f} GB | {rate:.0f} files/min", flush=True)

    elapsed = (datetime.now() - start).total_seconds() / 60
    summary = (
        f"\nHarvest (WSL) complete: {datetime.now()}\n"
        f"Elapsed:      {elapsed:.1f} minutes\n"
        f"Files copied: {copied}\n"
        f"Errors:       {errors}\n"
        f"Total size:   {total_bytes / 1073741824:.2f} GB\n"
        f"Progress log: {progress_file}\n"
    )
    print(summary)
    with open(log_file, 'a', encoding='utf-8') as lf:
        lf.write(summary)
        if error_list:
            lf.write("\nErrors (first 50):\n")
            for e in error_list:
                lf.write(f"  {e}\n")

    if errors:
        print(f"First {min(len(error_list), 20)} errors:")
        for e in error_list[:20]:
            print(f"  {e}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
