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
  const drive = db.query(
    `SELECT d.drive_code, d.label FROM drives d WHERE d.drive_code = ?`
  ).get(driveCode) as { drive_code: string; label: string } | null;

  if (!drive) return null;

  const stats = db.query(`
    SELECT
      (SELECT COALESCE(SUM(s2.file_count), 0) FROM scans s2
       JOIN drives d2 ON s2.drive_id = d2.drive_id WHERE d2.drive_code = ?) as file_count,
      SUM(f.size_bytes) as total_size,
      MIN(f.modified_date) as oldest_file,
      MAX(f.modified_date) as newest_file
    FROM files f
    JOIN scans s ON f.scan_id = s.scan_id
    JOIN drives d ON s.drive_id = d.drive_id
    WHERE d.drive_code = ?
  `).get(driveCode, driveCode) as any;

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

  const hash = db.query(
    `SELECT hash_value FROM file_hashes WHERE file_id = ? AND hash_type = 'sha256' LIMIT 1`
  ).get(fileId) as { hash_value: string } | null;

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
