# MCP Archive Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Standalone MCP server exposing five read-only tools (search_files, list_drives, drive_summary, get_file, check_hash) over stdio, backed by archive.db and a pull-through file cache.

**Architecture:** Single-process TypeScript MCP server using `@modelcontextprotocol/sdk` with stdio transport. Bun runtime. Read-only SQLite via `bun:sqlite`. File cache at configurable path. No Express dependency.

**Tech Stack:** TypeScript, Bun, `@modelcontextprotocol/sdk`, `bun:sqlite`, `bun:test`

**Spec:** `docs/superpowers/specs/2026-04-13-mcp-archive-server-design.md`

**Bead:** da-kh2

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/mcp/index.ts` | Server setup, tool routing, stdio transport |
| `src/mcp/queries.ts` | All SQLite query functions (read-only) |
| `src/mcp/cache.ts` | File cache: check, pull, path resolution |
| `src/mcp/__tests__/queries.test.ts` | Unit tests for query functions |
| `src/mcp/__tests__/cache.test.ts` | Unit tests for cache logic |
| `scripts/windows/da-mcp.cmd` | Windows launcher for Claude Desktop/Cowork |

---

### Task 1: Install MCP SDK and scaffold files

**Files:**
- Modify: `package.json`
- Create: `src/mcp/index.ts`
- Create: `src/mcp/queries.ts`
- Create: `src/mcp/cache.ts`

- [ ] **Step 1: Install MCP SDK**

```bash
cd /root/projects/DataArchive
bun add @modelcontextprotocol/sdk
```

- [ ] **Step 2: Create empty module files**

Create `src/mcp/queries.ts`:
```typescript
// SQLite query functions for MCP server
import { Database } from "bun:sqlite";

export function openDb(dbPath: string): Database {
  return new Database(dbPath, { readonly: true });
}
```

Create `src/mcp/cache.ts`:
```typescript
// File cache for MCP get_file tool
export const DEFAULT_CACHE_PATH = process.platform === "win32"
  ? "C:\\DataArchive-cache"
  : "/tmp/DataArchive-cache";
```

Create `src/mcp/index.ts`:
```typescript
// DataArchive MCP Server - entry point
console.error("DataArchive MCP server starting...");
```

- [ ] **Step 3: Verify bun can run the entry point**

```bash
bun run src/mcp/index.ts
```

Expected: prints "DataArchive MCP server starting..." to stderr, then exits.

- [ ] **Step 4: Commit**

```bash
git add package.json bun.lockb src/mcp/
git commit -m "chore: scaffold MCP server with SDK dependency [da-kh2]"
```

---

### Task 2: SQLite query layer

**Files:**
- Modify: `src/mcp/queries.ts`
- Create: `src/mcp/__tests__/queries.test.ts`

- [ ] **Step 1: Write failing tests for all five query functions**

Create `src/mcp/__tests__/queries.test.ts`:
```typescript
import { describe, test, expect, beforeAll, afterAll } from "bun:test";
import { Database } from "bun:sqlite";
import {
  openDb,
  searchFiles,
  listDrives,
  driveSummary,
  getFileInfo,
  checkHash,
} from "../queries";

let db: Database;

beforeAll(() => {
  // Create in-memory test database with realistic schema and data
  db = new Database(":memory:");
  db.exec(`
    CREATE TABLE drives (
      drive_id INTEGER PRIMARY KEY AUTOINCREMENT,
      serial_number TEXT UNIQUE,
      model TEXT,
      manufacturer TEXT,
      size_bytes INTEGER,
      filesystem TEXT,
      partition_scheme TEXT,
      label TEXT,
      connection_type TEXT,
      firmware_version TEXT,
      media_type TEXT,
      bus_type TEXT,
      notes TEXT,
      first_seen TIMESTAMP,
      last_scanned TIMESTAMP,
      drive_code TEXT
    );

    CREATE TABLE scans (
      scan_id INTEGER PRIMARY KEY AUTOINCREMENT,
      drive_id INTEGER,
      scan_start TIMESTAMP,
      scan_end TIMESTAMP,
      mount_point TEXT,
      file_count INTEGER,
      total_size_bytes INTEGER,
      status TEXT,
      FOREIGN KEY (drive_id) REFERENCES drives(drive_id)
    );

    CREATE TABLE files (
      file_id INTEGER PRIMARY KEY AUTOINCREMENT,
      scan_id INTEGER,
      path TEXT,
      size_bytes INTEGER,
      modified_date TIMESTAMP,
      created_date TIMESTAMP,
      accessed_date TIMESTAMP,
      extension TEXT,
      is_hidden BOOLEAN,
      is_system BOOLEAN,
      priority TEXT DEFAULT 'medium',
      FOREIGN KEY (scan_id) REFERENCES scans(scan_id)
    );

    CREATE TABLE file_hashes (
      hash_id INTEGER PRIMARY KEY AUTOINCREMENT,
      scan_id INTEGER NOT NULL,
      file_id INTEGER NOT NULL,
      hash_type TEXT NOT NULL,
      hash_value TEXT NOT NULL,
      computed_at TIMESTAMP NOT NULL
    );

    INSERT INTO drives (serial_number, model, drive_code, label, size_bytes, last_scanned)
    VALUES ('SN-001', 'Samsung 980 PRO', 'DVRC', 'C: boot', 1000000000, '2026-04-11');

    INSERT INTO scans (drive_id, scan_start, scan_end, mount_point, file_count, total_size_bytes, status)
    VALUES (1, '2026-04-11 15:30:00', '2026-04-11 19:46:00', '/mnt/c', 835249, 453000000000, 'COMPLETE');

    INSERT INTO files (scan_id, path, size_bytes, modified_date, extension)
    VALUES
      (1, 'Users/steve/Documents/report.pdf', 1048576, '2025-06-15', '.pdf'),
      (1, 'Users/steve/Code/TTS/app.cs', 4096, '2024-01-10', '.cs'),
      (1, 'Users/steve/Code/TTS/web.config', 2048, '2024-01-10', '.config'),
      (1, 'Users/steve/Downloads/photo.zip', 52428800, '2026-03-01', '.zip');

    INSERT INTO file_hashes (scan_id, file_id, hash_type, hash_value, computed_at)
    VALUES
      (1, 1, 'sha256', 'abc123def456', '2026-04-12'),
      (1, 2, 'sha256', 'fff000aaa111', '2026-04-12');
  `);
});

afterAll(() => {
  db.close();
});

describe("searchFiles", () => {
  test("matches pattern in path", () => {
    const results = searchFiles(db, { pattern: "TTS" });
    expect(results.length).toBe(2);
    expect(results[0].path).toContain("TTS");
  });

  test("filters by extension", () => {
    const results = searchFiles(db, { pattern: "Users", extension: ".pdf" });
    expect(results.length).toBe(1);
    expect(results[0].extension).toBe(".pdf");
  });

  test("filters by drive_code", () => {
    const results = searchFiles(db, { pattern: "Users", drive_code: "DVRC" });
    expect(results.length).toBe(4);
  });

  test("respects limit", () => {
    const results = searchFiles(db, { pattern: "Users", limit: 2 });
    expect(results.length).toBe(2);
  });
});

describe("listDrives", () => {
  test("returns all drives with file counts", () => {
    const drives = listDrives(db);
    expect(drives.length).toBe(1);
    expect(drives[0].drive_code).toBe("DVRC");
    expect(drives[0].file_count).toBe(835249);
  });
});

describe("driveSummary", () => {
  test("returns stats for a drive", () => {
    const summary = driveSummary(db, "DVRC");
    expect(summary).not.toBeNull();
    expect(summary!.drive_code).toBe("DVRC");
    expect(summary!.file_count).toBe(835249);
    expect(summary!.scan_count).toBe(1);
  });

  test("returns null for unknown drive", () => {
    const summary = driveSummary(db, "XXXX");
    expect(summary).toBeNull();
  });
});

describe("getFileInfo", () => {
  test("returns file with mount point", () => {
    const info = getFileInfo(db, 1);
    expect(info).not.toBeNull();
    expect(info!.path).toBe("Users/steve/Documents/report.pdf");
    expect(info!.mount_point).toBe("/mnt/c");
    expect(info!.drive_code).toBe("DVRC");
  });

  test("returns null for unknown file_id", () => {
    expect(getFileInfo(db, 99999)).toBeNull();
  });
});

describe("checkHash", () => {
  test("finds existing hash", () => {
    const result = checkHash(db, "abc123def456");
    expect(result.exists).toBe(true);
    expect(result.matches.length).toBe(1);
    expect(result.matches[0].path).toContain("report.pdf");
  });

  test("returns empty for unknown hash", () => {
    const result = checkHash(db, "deadbeef");
    expect(result.exists).toBe(false);
    expect(result.matches.length).toBe(0);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
bun test src/mcp/__tests__/queries.test.ts
```

Expected: FAIL — functions not yet exported from queries.ts.

- [ ] **Step 3: Implement all query functions**

Update `src/mcp/queries.ts`:
```typescript
import { Database } from "bun:sqlite";

export function openDb(dbPath: string): Database {
  return new Database(dbPath, { readonly: true });
}

export interface FileResult {
  file_id: number;
  drive_code: string;
  path: string;
  size_bytes: number;
  modified_date: string;
  extension: string;
}

export interface SearchParams {
  pattern: string;
  drive_code?: string;
  extension?: string;
  limit?: number;
}

export function searchFiles(db: Database, params: SearchParams): FileResult[] {
  const { pattern, drive_code, extension, limit = 100 } = params;
  let sql = `
    SELECT f.file_id, d.drive_code, f.path, f.size_bytes, f.modified_date, f.extension
    FROM files f
    JOIN scans s ON f.scan_id = s.scan_id
    JOIN drives d ON s.drive_id = d.drive_id
    WHERE f.path LIKE ?`;
  const bindings: any[] = [`%${pattern}%`];

  if (drive_code) {
    sql += ` AND d.drive_code = ?`;
    bindings.push(drive_code);
  }
  if (extension) {
    sql += ` AND LOWER(f.extension) = LOWER(?)`;
    bindings.push(extension);
  }
  sql += ` ORDER BY f.modified_date DESC LIMIT ?`;
  bindings.push(limit);

  return db.query(sql).all(...bindings) as FileResult[];
}

export interface DriveResult {
  drive_id: number;
  drive_code: string;
  label: string;
  serial_number: string;
  model: string;
  size_bytes: number;
  last_scanned: string;
  file_count: number;
}

export function listDrives(db: Database): DriveResult[] {
  return db.query(`
    SELECT d.drive_id, d.drive_code, d.label, d.serial_number, d.model,
           d.size_bytes, d.last_scanned, s.file_count
    FROM drives d
    LEFT JOIN scans s ON d.drive_id = s.drive_id AND s.status = 'COMPLETE'
      AND s.scan_id = (SELECT MAX(s2.scan_id) FROM scans s2 WHERE s2.drive_id = d.drive_id AND s2.status = 'COMPLETE')
    WHERE d.drive_code IS NOT NULL
    ORDER BY d.drive_code
  `).all() as DriveResult[];
}

export interface DriveSummaryResult {
  drive_code: string;
  label: string;
  file_count: number;
  total_size: number;
  oldest_file: string;
  newest_file: string;
  top_extensions: string[];
  scan_count: number;
}

export function driveSummary(db: Database, driveCode: string): DriveSummaryResult | null {
  const drive = db.query(`
    SELECT d.drive_code, d.label FROM drives d WHERE d.drive_code = ?
  `).get(driveCode) as { drive_code: string; label: string } | null;

  if (!drive) return null;

  const stats = db.query(`
    SELECT COUNT(*) as file_count, SUM(f.size_bytes) as total_size,
           MIN(f.modified_date) as oldest_file, MAX(f.modified_date) as newest_file
    FROM files f
    JOIN scans s ON f.scan_id = s.scan_id
    JOIN drives d ON s.drive_id = d.drive_id
    WHERE d.drive_code = ?
  `).get(driveCode) as any;

  const scanCount = db.query(`
    SELECT COUNT(*) as n FROM scans s
    JOIN drives d ON s.drive_id = d.drive_id
    WHERE d.drive_code = ? AND s.status = 'COMPLETE'
  `).get(driveCode) as { n: number };

  const topExt = db.query(`
    SELECT f.extension, COUNT(*) as n
    FROM files f JOIN scans s ON f.scan_id = s.scan_id JOIN drives d ON s.drive_id = d.drive_id
    WHERE d.drive_code = ? AND f.extension != ''
    GROUP BY f.extension ORDER BY n DESC LIMIT 10
  `).all(driveCode) as { extension: string; n: number }[];

  return {
    drive_code: drive.drive_code,
    label: drive.label,
    file_count: stats.file_count || 0,
    total_size: stats.total_size || 0,
    oldest_file: stats.oldest_file || "",
    newest_file: stats.newest_file || "",
    top_extensions: topExt.map((r) => r.extension),
    scan_count: scanCount.n,
  };
}

export interface FileInfo {
  file_id: number;
  path: string;
  size_bytes: number;
  mount_point: string;
  drive_code: string;
  sha256: string | null;
}

export function getFileInfo(db: Database, fileId: number): FileInfo | null {
  const row = db.query(`
    SELECT f.file_id, f.path, f.size_bytes, s.mount_point, d.drive_code
    FROM files f
    JOIN scans s ON f.scan_id = s.scan_id
    JOIN drives d ON s.drive_id = d.drive_id
    WHERE f.file_id = ?
    ORDER BY s.scan_id DESC LIMIT 1
  `).get(fileId) as any;

  if (!row) return null;

  const hash = db.query(`
    SELECT hash_value FROM file_hashes
    WHERE file_id = ? AND hash_type = 'sha256' LIMIT 1
  `).get(fileId) as { hash_value: string } | null;

  return { ...row, sha256: hash?.hash_value ?? null };
}

export interface HashCheckResult {
  exists: boolean;
  matches: { file_id: number; drive_code: string; path: string }[];
}

export function checkHash(db: Database, sha256: string): HashCheckResult {
  const matches = db.query(`
    SELECT f.file_id, d.drive_code, f.path
    FROM file_hashes fh
    JOIN files f ON fh.file_id = f.file_id
    JOIN scans s ON f.scan_id = s.scan_id
    JOIN drives d ON s.drive_id = d.drive_id
    WHERE fh.hash_type = 'sha256' AND fh.hash_value = ?
  `).all(sha256) as { file_id: number; drive_code: string; path: string }[];

  return { exists: matches.length > 0, matches };
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
bun test src/mcp/__tests__/queries.test.ts
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/mcp/queries.ts src/mcp/__tests__/queries.test.ts
git commit -m "feat(mcp): implement query layer with tests [da-kh2]"
```

---

### Task 3: File cache layer

**Files:**
- Modify: `src/mcp/cache.ts`
- Create: `src/mcp/__tests__/cache.test.ts`

- [ ] **Step 1: Write failing tests for cache operations**

Create `src/mcp/__tests__/cache.test.ts`:
```typescript
import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { mkdtempSync, writeFileSync, rmSync, existsSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { FileCache } from "../cache";

let cacheDir: string;
let sourceDir: string;
let cache: FileCache;

beforeEach(() => {
  cacheDir = mkdtempSync(join(tmpdir(), "da-cache-"));
  sourceDir = mkdtempSync(join(tmpdir(), "da-source-"));
  cache = new FileCache(cacheDir);
});

afterEach(() => {
  rmSync(cacheDir, { recursive: true, force: true });
  rmSync(sourceDir, { recursive: true, force: true });
});

describe("FileCache", () => {
  test("cachePath builds correct path", () => {
    const p = cache.cachePath("DVRC", "Users/steve/doc.pdf");
    expect(p).toBe(join(cacheDir, "DVRC", "Users", "steve", "doc.pdf"));
  });

  test("isCached returns false for missing file", () => {
    expect(cache.isCached("DVRC", "nope.txt")).toBe(false);
  });

  test("pullFile copies source to cache and returns path", async () => {
    const srcFile = join(sourceDir, "test.txt");
    writeFileSync(srcFile, "hello world");

    const result = await cache.pullFile("TEST", "test.txt", srcFile);
    expect(result.cache_path).toBe(join(cacheDir, "TEST", "test.txt"));
    expect(existsSync(result.cache_path)).toBe(true);
    expect(result.size_bytes).toBe(11);
  });

  test("pullFile returns cached path on second call without re-copying", async () => {
    const srcFile = join(sourceDir, "test.txt");
    writeFileSync(srcFile, "hello world");

    await cache.pullFile("TEST", "test.txt", srcFile);
    // Delete source — cache hit should still work
    rmSync(srcFile);

    const result = await cache.pullFile("TEST", "test.txt", srcFile);
    expect(existsSync(result.cache_path)).toBe(true);
  });

  test("pullFile returns error for unreachable source", async () => {
    const result = await cache.pullFile("TEST", "nope.txt", "/nonexistent/path/nope.txt");
    expect(result.error).toBeDefined();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
bun test src/mcp/__tests__/cache.test.ts
```

Expected: FAIL — FileCache not yet exported.

- [ ] **Step 3: Implement FileCache**

Update `src/mcp/cache.ts`:
```typescript
import { existsSync, mkdirSync, statSync } from "node:fs";
import { copyFile } from "node:fs/promises";
import { join, dirname } from "node:path";

export const DEFAULT_CACHE_PATH =
  process.platform === "win32" ? "C:\\DataArchive-cache" : "/tmp/DataArchive-cache";

export interface PullResult {
  cache_path: string;
  size_bytes: number;
  error?: string;
}

export class FileCache {
  private root: string;

  constructor(root?: string) {
    this.root = root ?? process.env.DA_CACHE_PATH ?? DEFAULT_CACHE_PATH;
  }

  cachePath(driveCode: string, relativePath: string): string {
    return join(this.root, driveCode, ...relativePath.split("/"));
  }

  isCached(driveCode: string, relativePath: string): boolean {
    return existsSync(this.cachePath(driveCode, relativePath));
  }

  async pullFile(
    driveCode: string,
    relativePath: string,
    sourcePath: string
  ): Promise<PullResult> {
    const dest = this.cachePath(driveCode, relativePath);

    // Cache hit
    if (existsSync(dest)) {
      const stat = statSync(dest);
      return { cache_path: dest, size_bytes: stat.size };
    }

    // Source check
    if (!existsSync(sourcePath)) {
      return { cache_path: "", size_bytes: 0, error: `Source unreachable: ${sourcePath}` };
    }

    // Copy
    try {
      mkdirSync(dirname(dest), { recursive: true });
      await copyFile(sourcePath, dest);
      const stat = statSync(dest);
      return { cache_path: dest, size_bytes: stat.size };
    } catch (err: any) {
      return { cache_path: "", size_bytes: 0, error: err.message };
    }
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
bun test src/mcp/__tests__/cache.test.ts
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/mcp/cache.ts src/mcp/__tests__/cache.test.ts
git commit -m "feat(mcp): implement file cache with tests [da-kh2]"
```

---

### Task 4: MCP server with tool handlers

**Files:**
- Modify: `src/mcp/index.ts`

- [ ] **Step 1: Implement the full MCP server**

Update `src/mcp/index.ts`:
```typescript
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  ListToolsRequestSchema,
  CallToolRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { resolve } from "node:path";
import { openDb, searchFiles, listDrives, driveSummary, getFileInfo, checkHash } from "./queries";
import { FileCache } from "./cache";

const dbPath = process.env.DA_DB_PATH ?? resolve(__dirname, "../../data/archive.db");
const db = openDb(dbPath);
const cache = new FileCache();

const server = new Server(
  { name: "data-archive", version: "1.0.0" },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "search_files",
      description: "Search the file catalog by pattern, extension, or drive code",
      inputSchema: {
        type: "object" as const,
        properties: {
          pattern: { type: "string", description: "Substring matched against file path" },
          drive_code: { type: "string", description: "Narrow to one drive" },
          extension: { type: "string", description: "Filter by extension (e.g. '.cs')" },
          limit: { type: "number", description: "Max results (default 100)" },
        },
        required: ["pattern"],
      },
    },
    {
      name: "list_drives",
      description: "List all scanned drives with file counts",
      inputSchema: { type: "object" as const, properties: {} },
    },
    {
      name: "drive_summary",
      description: "Stats and profile for a single drive",
      inputSchema: {
        type: "object" as const,
        properties: {
          drive_code: { type: "string", description: "Drive code to summarize" },
        },
        required: ["drive_code"],
      },
    },
    {
      name: "get_file",
      description: "Pull a file into local cache and return its path",
      inputSchema: {
        type: "object" as const,
        properties: {
          file_id: { type: "number", description: "File ID from the catalog" },
        },
        required: ["file_id"],
      },
    },
    {
      name: "check_hash",
      description: "Check if a SHA-256 hash exists anywhere in the archive",
      inputSchema: {
        type: "object" as const,
        properties: {
          sha256: { type: "string", description: "SHA-256 hash to look up" },
        },
        required: ["sha256"],
      },
    },
  ],
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    switch (name) {
      case "search_files": {
        const results = searchFiles(db, {
          pattern: args!.pattern as string,
          drive_code: args!.drive_code as string | undefined,
          extension: args!.extension as string | undefined,
          limit: args!.limit as number | undefined,
        });
        return { content: [{ type: "text", text: JSON.stringify(results, null, 2) }] };
      }

      case "list_drives": {
        const drives = listDrives(db);
        return { content: [{ type: "text", text: JSON.stringify(drives, null, 2) }] };
      }

      case "drive_summary": {
        const summary = driveSummary(db, args!.drive_code as string);
        if (!summary) {
          return { content: [{ type: "text", text: `No drive found with code: ${args!.drive_code}` }], isError: true };
        }
        return { content: [{ type: "text", text: JSON.stringify(summary, null, 2) }] };
      }

      case "get_file": {
        const info = getFileInfo(db, args!.file_id as number);
        if (!info) {
          return { content: [{ type: "text", text: `No file found with ID: ${args!.file_id}` }], isError: true };
        }
        const sourcePath = `${info.mount_point}/${info.path}`;
        const result = await cache.pullFile(info.drive_code, info.path, sourcePath);
        if (result.error) {
          return { content: [{ type: "text", text: result.error }], isError: true };
        }
        return {
          content: [{ type: "text", text: JSON.stringify({
            cache_path: result.cache_path,
            size_bytes: result.size_bytes,
            sha256: info.sha256,
          }, null, 2) }],
        };
      }

      case "check_hash": {
        const result = checkHash(db, args!.sha256 as string);
        return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
      }

      default:
        return { content: [{ type: "text", text: `Unknown tool: ${name}` }], isError: true };
    }
  } catch (err: any) {
    return { content: [{ type: "text", text: `Error: ${err.message}` }], isError: true };
  }
});

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("DataArchive MCP server running on stdio");
}

main().catch(console.error);
```

- [ ] **Step 2: Verify the server starts and lists tools**

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' | bun run src/mcp/index.ts 2>/dev/null | head -1
```

Expected: JSON response with server capabilities.

- [ ] **Step 3: Commit**

```bash
git add src/mcp/index.ts
git commit -m "feat(mcp): implement MCP server with five tool handlers [da-kh2]"
```

---

### Task 5: Windows launcher

**Files:**
- Create: `scripts/windows/da-mcp.cmd`

- [ ] **Step 1: Create the launcher**

Create `scripts/windows/da-mcp.cmd`:
```batch
@echo off
REM DataArchive MCP Server launcher for Windows consumers
REM Used by Claude Desktop, Cowork, and Windows zgents
wsl -d Zgent bun run /root/projects/DataArchive/src/mcp/index.ts
```

- [ ] **Step 2: Deploy to C:\Tools**

```bash
cp /root/projects/DataArchive/scripts/windows/da-mcp.cmd /mnt/c/Tools/da-mcp.cmd
```

- [ ] **Step 3: Commit**

```bash
git add scripts/windows/da-mcp.cmd
git commit -m "feat(mcp): add Windows launcher for Claude Desktop/Cowork [da-kh2]"
```

---

### Task 6: Integration smoke test

**Files:** none (manual verification)

- [ ] **Step 1: Test search_files against real database**

```bash
DA_DB_PATH=/root/projects/DataArchive/data/archive.db bun run src/mcp/index.ts <<'EOF'
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"search_files","arguments":{"pattern":"TTS","extension":".cs","limit":5}}}
EOF
```

Expected: JSON response with TTS .cs files from archive.db.

- [ ] **Step 2: Test list_drives against real database**

```bash
DA_DB_PATH=/root/projects/DataArchive/data/archive.db bun run src/mcp/index.ts <<'EOF'
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"list_drives","arguments":{}}}
EOF
```

Expected: JSON with DVRC, Tera1A, WWYY, and other drive records.

- [ ] **Step 3: Test check_hash against real database**

```bash
# Get a known hash first
HASH=$(sqlite3 /root/projects/DataArchive/data/archive.db "SELECT hash_value FROM file_hashes LIMIT 1;")
DA_DB_PATH=/root/projects/DataArchive/data/archive.db bun run src/mcp/index.ts <<EOF
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"check_hash","arguments":{"sha256":"$HASH"}}}
EOF
```

Expected: `exists: true` with at least one match.

---

### Task 7: Register in DataArchive settings

**Files:**
- Modify: `.claude/settings.json`

- [ ] **Step 1: Add MCP server to DataArchive's own settings**

Add to `.claude/settings.json` under `mcpServers`:
```json
{
  "mcpServers": {
    "data-archive": {
      "command": "bun",
      "args": ["run", "/root/projects/DataArchive/src/mcp/index.ts"],
      "env": {
        "DA_DB_PATH": "/root/projects/DataArchive/data/archive.db"
      }
    }
  }
}
```

- [ ] **Step 2: Add tool permissions to allowedTools**

Add to the `allow` list in `.claude/settings.json`:
```
"mcp__data-archive__search_files",
"mcp__data-archive__list_drives",
"mcp__data-archive__drive_summary",
"mcp__data-archive__get_file",
"mcp__data-archive__check_hash"
```

- [ ] **Step 3: Commit**

```bash
git add .claude/settings.json
git commit -m "feat(mcp): register data-archive MCP server in settings [da-kh2]"
```
