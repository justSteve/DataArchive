# DataArchive MCP Server Design

**Bead:** da-kh2
**Date:** 2026-04-13
**Status:** Approved

## Purpose

Expose DataArchive's catalog and file retrieval capabilities to the Gas City enterprise. Any zgent, Claude Desktop, or Cowork instance can search the archive, check for duplicates, and pull files from scanned drives — without depending on the Express API or needing direct database access.

## Architecture

Standalone TypeScript MCP server using `@modelcontextprotocol/sdk` with stdio transport. Opens a read-only SQLite connection to `data/archive.db`. Manages a local file cache for pulled files.

```
Consumer (zgent / Claude Desktop / Cowork)
    |
    +-- stdio --> DataArchive MCP Server
                      |-- SQLite (read-only) --> data/archive.db
                      +-- File cache
                            |-- copy from F: or Z: on demand
                            +-- configurable path
```

No dependency on the Express API. No web server. No daemon. Each consumer spawns its own instance via stdio — lightweight since the workload is read-only SQLite queries and occasional single-file copies.

## MCP Tools

Five tools, all read-only. No mutations to the archive.

### search_files

Search the file catalog by pattern, extension, or drive.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| pattern | string | yes | Substring matched against file path (server wraps in `%pattern%` for SQL LIKE) |
| drive_code | string | no | Narrow to one drive |
| extension | string | no | Filter by file extension (e.g. ".cs") |
| limit | int | no | Max results, default 100 |

Returns: `[{file_id, drive_code, path, size_bytes, modified_date, extension}]`

### list_drives

List all scanned drives.

No parameters.

Returns: `[{drive_id, drive_code, label, serial_number, model, size_bytes, last_scanned, file_count}]`

File count is derived via join to scans table.

### drive_summary

Stats and profile for a single drive.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| drive_code | string | yes | Drive code to summarize |

Returns: `{drive_code, label, file_count, total_size, oldest_file, newest_file, top_extensions[], scan_count}`

### get_file

Pull a file into the local cache and return its path.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| file_id | int | yes | File ID from the catalog |

Behavior:
1. Look up file path and drive mount info from `files` + `scans` tables (most recent scan's mount_point for the drive).
2. Check if `{cache_root}/{drive_code}/{relative_path}` exists. If yes, return immediately.
3. If not cached, copy from source mount. Create parent directories on demand.
4. If source mount is unreachable (drive not docked, NAS offline), return a clear error — no hang.

Returns: `{cache_path, size_bytes, sha256}` or `{error: "..."}`.

Copy method: `fs.copyFile` (single-file pull, not bulk).

### check_hash

Check if a SHA-256 hash exists anywhere in the archive.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| sha256 | string | yes | SHA-256 hash to look up |

Returns: `{exists: bool, matches: [{file_id, drive_code, path}]}`

## File Cache

### Structure

```
{cache_root}/
  {drive_code}/
    {relative_path}
```

Mirrors the source drive layout. Example: `C:\DataArchive-cache\DVRC\Users\steve\OneDrive\Documents\report.pdf`

### Behavior

- Pull-through on `get_file` — copy on first request, serve from cache on subsequent requests.
- No automatic eviction. Traffic profile is infrequent, batch-oriented, MB-scale. Cache grows until manually cleared.
- A `clear_cache` admin tool can be added later if needed, but is not part of the initial build.

### Configuration

Read from environment variables or a config file:

| Setting | Env var | Default |
|---------|---------|---------|
| Cache path | `DA_CACHE_PATH` | `C:\DataArchive-cache` |
| Database path | `DA_DB_PATH` | `data/archive.db` (relative to server cwd) |

Post-repave, update the cache path to wherever makes sense on the fresh C: or move to a different drive.

## Consumer Registration

### WSL zgents

Direct invocation via bun:

```json
{
  "mcpServers": {
    "data-archive": {
      "command": "bun",
      "args": ["run", "/root/projects/DataArchive/src/mcp/index.ts"]
    }
  }
}
```

### Windows consumers (Claude Desktop, Cowork, Windows zgents)

Launcher at `C:\Tools\da-mcp.cmd` wraps the invocation so registration is short:

```json
{
  "mcpServers": {
    "data-archive": {
      "command": "C:\\Tools\\da-mcp.cmd"
    }
  }
}
```

The launcher invokes `wsl -d Zgent bun run /root/projects/DataArchive/src/mcp/index.ts`, handling the WSL-to-Windows boundary.

### Tool permissions

Add to each consumer's `allowedTools`:
- `mcp__data-archive__search_files`
- `mcp__data-archive__list_drives`
- `mcp__data-archive__drive_summary`
- `mcp__data-archive__get_file`
- `mcp__data-archive__check_hash`

No per-zgent or per-tool restrictions. Universal read-only access.

## Access Model

All tools are read-only. No tool mutates the archive or the database. No ACL, no authentication, no rate limiting. Any consumer in the enterprise has full access to all five tools.

The only platform consideration is invocation path (WSL source vs Windows launcher), not authorization.

## Implementation Scope

### In scope
- `src/mcp/index.ts` — MCP server with five tool handlers
- SQLite read-only connection with query functions
- File cache with pull-through copy and configurable root
- `C:\Tools\da-mcp.cmd` — Windows launcher
- Build step to produce `dist/mcp-server.js`

### Out of scope
- Cache eviction / size limits (not needed at current traffic profile)
- Write operations (no scan triggering, no harvest management via MCP)
- Streaming / chunked file transfer (files are MB-scale, copy-and-return is sufficient)
- Authentication (enterprise is trusted, all tools are read-only)

## Reference

- CSO/convo-archive MCP server at `/root/projects/CSO/mcp-servers/convo-archive/` — proven pattern using `@modelcontextprotocol/sdk` with stdio transport.
- `@modelcontextprotocol/sdk` v1.0.1+
- Runtime: Bun
