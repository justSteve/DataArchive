// SQLite query functions for MCP server
import { Database } from "bun:sqlite";

export function openDb(dbPath: string): Database {
  return new Database(dbPath, { readonly: true });
}
