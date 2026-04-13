// File cache for MCP get_file tool
export const DEFAULT_CACHE_PATH = process.platform === "win32"
  ? "C:\\DataArchive-cache"
  : "/tmp/DataArchive-cache";
