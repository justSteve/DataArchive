import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  ListToolsRequestSchema,
  CallToolRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { resolve } from "node:path";
import { openDb, searchFiles, listDrives, driveSummary, getFileInfo, checkHash } from "./queries";
import { FileCache } from "./cache";

const dbPath = process.env.DA_DB_PATH ?? resolve(import.meta.dir, "../../data/archive.db");
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
