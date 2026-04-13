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
    rmSync(srcFile);
    const result = await cache.pullFile("TEST", "test.txt", srcFile);
    expect(existsSync(result.cache_path)).toBe(true);
  });

  test("pullFile returns error for unreachable source", async () => {
    const result = await cache.pullFile("TEST", "nope.txt", "/nonexistent/path/nope.txt");
    expect(result.error).toBeDefined();
  });
});
