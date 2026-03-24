# DataArchive — Persistent Storage and Retrieval Service

**Zgent Status:** zgent (in-process toward Zgent certification)
**Role:** Service Provider (Tier 1) — enterprise data archival, drive inspection, artifact storage
**Bead Prefix:** `DataArchive`

## STOP — Beads Gate (Read This First)

You are a beads-first entity. Before doing substantive work, check for an open bead:

```bash
bd ready              # See available work
bd create -t "title"  # Create a new bead if none covers your work
bd update <id> --status in_progress  # Claim work
bd close <id>         # Mark work complete
bd sync               # Sync beads changes with git
```

**This is not optional.** No bead = no work. Reference the bead ID in all commit messages:
```
fix: repair scan pipeline [DataArchive-xxx]
```

## Intent

This project exists to consolidate a lifetime of digital history — dozens of
drives spanning the early 1990s to present — into a single, coherent personal
archive on Z:.

Claude's role is **archivist**, not tool operator. When presented with a drive:

1. **Explore it like an archaeologist.** What era? What was Steve doing? What
   kind of machine was this? What matters here?
2. **Place it in context** against everything already cataloged. What's new?
   What's duplicate? What fills gaps?
3. **Tell the story** before cataloging the bits. The output is narrative first,
   data second.

Steve declares intent. Claude decides how to get there — what tools to build,
what inspection techniques to use, what order to process drives, what depth
each one needs. The toolset evolves as we learn what these drives contain.

## What This Is

DataArchive v2 is a **Claude-assisted interactive drive inspection system** using a polyglot two-tier architecture. It provides persistent storage, retrieval, and analysis of drive contents across the enterprise.

## Architecture

- **Infrastructure Layer (TypeScript)**: Express API server + React UI
- **Domain Layer (Python)**: Multi-pass inspection, file scanning, hardware detection, OS detection
- **Integration**: TypeScript spawns Python processes via `child_process.spawn()` with JSON over stdout/stderr
- **Database**: Shared SQLite database (`output/archive.db`)
- **Runtime**: Bun (migrated from Node.js)

## Multi-Pass Inspection Workflow

| Pass | Purpose | Output |
|------|---------|--------|
| **1. Health** | chkdsk-level inspection, error handling | Health report |
| **2. OS Detection** | Windows boot/version via registry | Exact build/edition |
| **3. Metadata** | Full folder/file metadata capture | File catalog |
| **4. Review** | Claude-assisted decisions, duplicates | Decision report |

## What Every Claude Instance Must Understand

1. **Beads-first is non-negotiable.** No substantive work without an authorizing bead.
2. **This is an independent zgent**, not a Gas Town managed agent. Use `bd` commands, not `gt` commands.
3. **Polyglot architecture** — TypeScript infrastructure, Python domain. JSON over stdout/stderr for IPC.
4. **SQLite concurrency** — Python writes during inspections, TypeScript reads for API. One writer at a time.
5. **Process communication** — always use JSON, always use `--json-output` flag, never use shell strings.

## Service Contract

### Data Capabilities
- Drive inspection and cataloging (multi-pass)
- File metadata capture and deduplication
- Hardware detection and health reporting
- Report generation for Claude analysis

### Key Integration Points
- **PythonBridge** (`src/services/PythonBridge.ts`): TS<>Python process spawning
- **DatabaseService**: SQLite access layer
- **Reports**: Generated to `output/reports/` in markdown format

## Graduation Status

- [x] Beads installed and functional
- [x] AGENTS.md with bd quick reference
- [x] CLAUDE.md beads gate (this deployment)
- [x] .claude/rules deployed
- [x] .claude/settings.json deployed
- [x] .gitattributes full template
- [ ] ECC session registered
- [ ] MCP server (expose query API)
- [ ] Session boot script

## Development

```bash
# Start both API and frontend
./scripts/shell/start-dev.sh

# Or manually:
bun run api          # API server on port 3001
bun run dev          # Frontend dev server on port 5173

# Build
bun run build

# Tests
bun test

# Python environment
cd python && source .venv/bin/activate
pip install -r requirements.txt
python inspect_drive.py E:\ --session-id 1
```

## Key Files

| Path | Purpose |
|------|---------|
| `src/services/PythonBridge.ts` | TS<>Python integration |
| `src/api/routes/` | Express API routes |
| `src/frontend/components/` | React UI components |
| `python/inspection/` | Multi-pass inspection modules |
| `python/core/` | Database, scanner, OS detector |
| `output/archive.db` | SQLite database |
| `output/reports/` | Generated inspection reports |
| `.beads/issues.jsonl` | Work authorization tracking |

## Important Constraints

### Process Communication
- **Always use JSON** for Python<>TypeScript data exchange
- **Always use `--json-output`** flag when calling Python scripts
- **Never use shell strings** — use argument arrays to prevent injection

### SQLite Concurrency
- Python writes during inspections/scans
- TypeScript reads for API queries
- Only one inspection/scan should write at a time
