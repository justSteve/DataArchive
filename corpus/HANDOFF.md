# HANDOFF — bead `da-5in` career corpus

You are a Claude session (or another agent) picking up an in-progress bead that
Steve does not want to re-explain. Everything you need is here.

## One-paragraph state

Goal: a cross-platform-accessible buffer of filtered files from Steve's drive
archive, organized by thread, committed to git so any model on any platform
can read it after cloning. Snapshot DB taken, filters defined, thread
discovery run (165 threads: 19 keyword + 146 directory), 6 thread buffers
materialized before the session was lost. This handoff was reconstructed by
the COO from a recovered terminal transcript after the Zgent distro was wiped.

## What exists (on origin, survived the wipe)

- `data/archive.db` — 2 GB SQLite catalog of the full drive archive (~3.9M files)
- `python/harvest_plan.py` — harvest execution planner
- Commits through `ebc5d7e` (2026-04-14) on `origin/main`

## What was lost (on Zgent distro, never committed)

All of the following need to be recreated:

1. **DB snapshot**: `data/snapshots/archive-20260417-0700.db` (2 GB checkpoint)
2. **Thread discovery script**: `python/discover_threads.py` (336 lines)
   - Reads archive.db, filters to authored-user slice (~2M files, 2.66 TB)
   - Applies exclusion regex (system dirs, build output, tool caches)
   - Produces keyword threads (19) + directory threads (146)
3. **Buffer materializer**: `python/materialize_buffer.py` (258 lines)
   - Given a thread_id, resolves DB paths to mounted drives
   - Copies matching files into `corpus/buffers/<thread_id>/`
   - Drive resolution order: /mnt/w/, /mnt/f/, /mnt/y/
   - Respects size budget (default 150 MB per thread)
4. **corpus/ directory** (the deliverable):
   - `AGENT_BRIEF.md` — entry point for incoming models (116 lines)
   - `DISCOVERED.md` — curated narrative with TTStrain corrections
   - `threads.jsonl` — 165 thread records
   - `threads/<id>/summary.md` — per-thread stubs
   - `marketing-artifacts.jsonl` — 4,398 TTS marketing artifacts
   - `discovery-notes.md`, `unthreaded_summary.md`
   - `buffers/kw-ttstrain/` — first materialized buffer (1,425 files, 31 MB)
   - `buffers/kw-picasa/`, `buffers/kw-flash/`, etc. — 5 more were in progress
5. **Steve-s_Sites clone**: `data/external/steve-s-sites/` from github.com/justSteve/Steve-s_Sites
6. **Bead `da-5in`** on Zgent's Dolt — needs recreation

## Harvest anomaly context

The staging root for harvested files flipped from `F:` to `W:` in commit `4c39b6d`
(2026-04-14). Consumers with hardcoded `F:\` paths see files as "missing" — they
are on `W:\<drive-label>\...`. Grep callers/dashboards for `F:\` references.

## Decisions Steve already made (do not re-ask)

1. **Scope**: all authored user data, not just TTStrain. Everything is target, priority determines order.
2. **Thread discovery**: discovery-first (agent proposes, Steve approves/renames), not dictated list.
3. **Buffer location**: `corpus/` at repo root, committed to git. NOT data/ (gitignored). NOT Z: (not cross-platform).
4. **Size posture**: soft-cap ~500 MB-1 GB per buffer. Real files where they fit, extracted text for large binaries.
5. **Thread summaries**: agents write them from sampling, not pre-authored. Only a handful need Steve's narrative (TTStrain done, Director Series, Mom's photos, Wedding — the rest are machine-derivable).
6. **TTStrain business arc** (Steve's own words): Flash compliance tutorials -> webinars -> diversification (banks, credit unions, Board of Directors). Single unified codebase spanning complete event lifecycle (promo, registration, delivery, billing) across 4 stakeholder audiences (end-users, affiliates, speakers, TTStrain hub). "Compliance Perspectives" = product name within TTStrain, not a predecessor business.
7. **BankWebinars/CUWebinars**: product-line deployments of the same codebase, not separate products. Merge under ttstrain thread.
8. **Second corpus source**: github.com/justSteve/Steve-s_Sites — `archived_pages/` (raw) and `sites/` (digested). Register as peer input alongside drive-derived catalog.

## Steps to resume (mechanical, no decisions needed)

### Step 1: Recreate snapshot
```bash
cp data/archive.db data/snapshots/archive-$(date +%Y%m%d-%H%M).db
```

### Step 2: Recreate discover_threads.py
Rewrite the thread discovery script. Key design:
- Read archive.db → filter to authored-user slice
- Exclusion regex for system dirs, build output, tool caches, ClaudeBackup
- Exclusion extensions: .dll, .exe, .sys, .pdb, .pyc, .so, .obj, etc.
- Keyword seeds: ttstrain, picasa, flash/swf/fla, itunes, outlook/pst, gmail/mbox, clipmate, resume, orchard, wedding, directors/education
- Directory clustering: group by top-2 path segments after drive root
- Output: threads.jsonl + threads/<id>/summary.md stubs

### Step 3: Recreate materialize_buffer.py
Rewrite the buffer materializer. Key design:
- Input: thread_id from threads.jsonl
- Query DB for matching files
- Resolve drive paths to /mnt/w/<code>/, /mnt/f/<code>/, /mnt/y/<code>/
- Copy into corpus/buffers/<thread_id>/files/
- Emit manifest.jsonl, copied.jsonl, copy-report.md
- Respect --budget-mb flag (default 150)
- Skip binaries over 10 MB, build output, obj/bin

### Step 4: Run discovery + materialize ttstrain first
```bash
python3 python/discover_threads.py --min-files 500
python3 python/materialize_buffer.py kw-ttstrain --budget-mb 150
```

### Step 5: Write AGENT_BRIEF.md and commit
Write the agent entry point, then commit the entire corpus/ tree.

## Do-nots

- Do NOT re-ask Steve to define threads or pick scope — decisions are above
- Do NOT treat the catalog as the deliverable — the BUFFER (actual files) is
- Do NOT put the buffer in data/ — it's gitignored and defeats the purpose
- Do NOT pre-author 300+ thread summaries — let downstream zgents do that work
- If anything surprising comes up, stop and write notes instead of improvising

## Success criteria

1. `corpus/` exists at repo root, in git, pushed to origin
2. At least kw-ttstrain buffer materialized with real .cs/.cshtml/.aspx files
3. AGENT_BRIEF.md exists and is readable by any incoming agent
4. A clone of this repo on cowork or cDesktop gives the agent real career material to work with
