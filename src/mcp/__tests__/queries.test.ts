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
  db = new Database(":memory:");
  db.exec(`
    CREATE TABLE drives (
      drive_id INTEGER PRIMARY KEY AUTOINCREMENT,
      serial_number TEXT UNIQUE, model TEXT, manufacturer TEXT, size_bytes INTEGER,
      filesystem TEXT, partition_scheme TEXT, label TEXT, connection_type TEXT,
      firmware_version TEXT, media_type TEXT, bus_type TEXT, notes TEXT,
      first_seen TIMESTAMP, last_scanned TIMESTAMP, drive_code TEXT
    );
    CREATE TABLE scans (
      scan_id INTEGER PRIMARY KEY AUTOINCREMENT, drive_id INTEGER, scan_start TIMESTAMP,
      scan_end TIMESTAMP, mount_point TEXT, file_count INTEGER, total_size_bytes INTEGER, status TEXT,
      FOREIGN KEY (drive_id) REFERENCES drives(drive_id)
    );
    CREATE TABLE files (
      file_id INTEGER PRIMARY KEY AUTOINCREMENT, scan_id INTEGER, path TEXT, size_bytes INTEGER,
      modified_date TIMESTAMP, created_date TIMESTAMP, accessed_date TIMESTAMP,
      extension TEXT, is_hidden BOOLEAN, is_system BOOLEAN, priority TEXT DEFAULT 'medium',
      FOREIGN KEY (scan_id) REFERENCES scans(scan_id)
    );
    CREATE TABLE file_hashes (
      hash_id INTEGER PRIMARY KEY AUTOINCREMENT, scan_id INTEGER NOT NULL, file_id INTEGER NOT NULL,
      hash_type TEXT NOT NULL, hash_value TEXT NOT NULL, computed_at TIMESTAMP NOT NULL
    );

    INSERT INTO drives (serial_number, model, drive_code, label, size_bytes, last_scanned)
    VALUES ('SN-001', 'Samsung 980 PRO', 'DVRC', 'C: boot', 1000000000, '2026-04-11');

    INSERT INTO scans (drive_id, scan_start, scan_end, mount_point, file_count, total_size_bytes, status)
    VALUES (1, '2026-04-11 15:30:00', '2026-04-11 19:46:00', '/mnt/c', 835249, 453000000000, 'COMPLETE');

    INSERT INTO files (scan_id, path, size_bytes, modified_date, extension) VALUES
      (1, 'Users/steve/Documents/report.pdf', 1048576, '2025-06-15', '.pdf'),
      (1, 'Users/steve/Code/TTS/app.cs', 4096, '2024-01-10', '.cs'),
      (1, 'Users/steve/Code/TTS/web.config', 2048, '2024-01-10', '.config'),
      (1, 'Users/steve/Downloads/photo.zip', 52428800, '2026-03-01', '.zip');

    INSERT INTO file_hashes (scan_id, file_id, hash_type, hash_value, computed_at) VALUES
      (1, 1, 'sha256', 'abc123def456', '2026-04-12'),
      (1, 2, 'sha256', 'fff000aaa111', '2026-04-12');
  `);
});

afterAll(() => { db.close(); });

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
    expect(driveSummary(db, "XXXX")).toBeNull();
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
