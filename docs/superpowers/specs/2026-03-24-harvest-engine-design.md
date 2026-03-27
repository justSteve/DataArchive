# Harvest Engine Design

## Overview

A two-stage hybrid engine for migrating files from scanned drives to the staging area (F:), with deduplication, logging, error handling, resume, and verification.

**Stage 1 — Python: Plan** → generates a manifest from archive.db
**Stage 2 — PowerShell: Execute** → copies files per the manifest, logs results

**Working directory:** `C:\myStuff\DataArchive\Harvester` (WSL: `/mnt/c/myStuff/DataArchive/Harvester`)
All configs, manifests, progress logs, and scripts live here. Python writes here; PowerShell reads/executes from here.

## Stage 1: Manifest Generator (Python)

`python/harvest_plan.py`

**Inputs:**
- Drive label (e.g., WWYY)
- Include/exclude rules (passed as a config dict or YAML)
- Staging root (default F:\)
- Prior manifests (for cross-drive dedup)

**Process:**
1. Query archive.db for all files on the target scan
2. Apply exclusion filters:
   - Extensions: .exe, .dll, .msi, .msp, .ocx, .sys, .drv, .com, .scr, .cpl, .iso, .cab, .cat
   - Paths: Boot/, $RECYCLE.BIN/, System Volume Information/, Windows/
   - Size: skip zero-byte files
3. Apply inclusion overrides (specific folders/extensions to always include regardless of other rules)
4. Dedup: check each file's SHA256 against a "claimed" set. The claimed set starts from any prior manifests already executed. First drive to claim a hash wins; subsequent occurrences are marked `skip:dupe`.
5. Output: `C:\myStuff\DataArchive\Harvester\manifests\harvest-<LABEL>.jsonl` — one JSON object per file:

```json
{"src": "D:\\Code\\TTSwebinars2\\Web.config", "dst": "F:\\WWYY\\Code\\TTSwebinars2\\Web.config", "size": 4523, "hash": "AB12...", "action": "copy"}
{"src": "D:\\Code\\_DLLs\\nunit.dll", "dst": null, "size": 12345, "hash": "CD34...", "action": "skip:ext"}
{"src": "D:\\Boot\\BCD", "dst": null, "size": 8192, "hash": "EF56...", "action": "skip:path"}
{"src": "D:\\Code\\file.cs", "dst": null, "size": 4523, "hash": "AB12...", "action": "skip:dupe", "dupe_of": "F:\\Tera1A\\Code\\file.cs"}
```

**Actions:** `copy`, `skip:ext`, `skip:path`, `skip:zero`, `skip:dupe`, `skip:size`

**Summary output to console:** counts per action, total copy size, estimated time.

**Inclusion config** lives in `C:\myStuff\DataArchive\Harvester\configs\<LABEL>.json`:

```json
{
  "label": "WWYY",
  "drive_letter": "D",
  "scan_id": 19,
  "include": ["Code", "Backups/restore", "Downloads/*.pdf", "Downloads/RestoreTarget", "Downloads/Video", "Video"],
  "include_root_ext": [".xls", ".zip"],
  "exclude_ext": [".exe", ".dll", ".msi", ".msp", ".ocx", ".sys", ".drv", ".com", ".scr", ".cpl", ".iso"],
  "exclude_paths": ["Boot", "$RECYCLE.BIN", "System Volume Information", "Windows"]
}
```

When `include` is specified, ONLY those paths are considered (whitelist mode). When omitted, everything except `exclude_paths` is considered.

## Stage 2: Manifest Executor (PowerShell)

`scripts/windows/harvest-execute.ps1`

**Inputs:**
- Manifest file path (the .jsonl from Stage 1)

**Script location:** `C:\myStuff\DataArchive\Harvester\harvest-execute.ps1`

**Process:**
1. Read manifest, filter to `action: "copy"` entries
2. Check for prior progress file (`C:\myStuff\DataArchive\Harvester\progress\harvest-<LABEL>.progress.jsonl`)
3. Resume: skip any files already in the progress log with status `done`
4. For each file:
   - Create destination directory if needed
   - Copy file
   - Verify: compare destination size to manifest size
   - Write result to progress log: `{"src": "...", "status": "done", "bytes": 4523}` or `{"src": "...", "status": "error", "error": "Access denied"}`
   - Console progress every 500 files
5. On completion: summary of copied/skipped/errored, total size

**Resume:** If interrupted and re-run, reads the progress log and skips completed files. Idempotent.

**Verification:** Size match on every copy. The progress log IS the verification record — any `status: "error"` entries are retried on next run.

**Post-harvest full hash verification** is available as a separate optional pass: re-hash everything in the destination and compare against manifest hashes. Not run by default — available for overnight/batch use.

## Workflow

```
# 1. Create drive config (or pass args)
# 2. Generate manifest (from WSL)
python harvest_plan.py --config /mnt/c/myStuff/DataArchive/Harvester/configs/WWYY.json

# 3. Review manifest summary (printed to console)
# 4. Execute (elevated PowerShell)
& C:\myStuff\DataArchive\Harvester\harvest-execute.ps1 -Manifest C:\myStuff\DataArchive\Harvester\manifests\harvest-WWYY.jsonl

# 5. Next drive — dedup is automatic via prior manifests
python harvest_plan.py --config /mnt/c/myStuff/DataArchive/Harvester/configs/Tera1A.json
```

## Cross-Drive Dedup

The manifest generator loads all prior progress logs from `C:\myStuff\DataArchive\Harvester\progress\` with `status: "done"` entries. It builds a set of claimed hashes → destination paths. When a new drive has a file with an already-claimed hash, it gets `action: "skip:dupe"` with a `dupe_of` reference.

This means drive processing order matters. First drive processed claims files. This is the intended behavior — process drives in chronological/priority order.

## File Inventory

| File | Language | Purpose |
|------|----------|---------|
| `python/harvest_plan.py` | Python | Manifest generator (runs in WSL) |
| `C:\myStuff\DataArchive\Harvester\configs\*.json` | JSON | Per-drive inclusion configs |
| `C:\myStuff\DataArchive\Harvester\harvest-execute.ps1` | PowerShell | Manifest executor with resume |
| `C:\myStuff\DataArchive\Harvester\manifests\harvest-<LABEL>.jsonl` | JSONL | Generated manifest |
| `C:\myStuff\DataArchive\Harvester\progress\harvest-<LABEL>.progress.jsonl` | JSONL | Execution progress/resume log |
