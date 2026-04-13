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

    if (existsSync(dest)) {
      const stat = statSync(dest);
      return { cache_path: dest, size_bytes: stat.size };
    }

    if (!existsSync(sourcePath)) {
      return { cache_path: "", size_bytes: 0, error: `Source unreachable: ${sourcePath}` };
    }

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
