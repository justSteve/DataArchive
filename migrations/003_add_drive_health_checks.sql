-- Migration: 003_add_drive_health_checks
-- Description: Add drive_health_checks table for pre-reformat health assessment
-- Created: 2026-05-02
-- Bead: da-ljz
--
-- Two check types populate this table:
--   'read_test'  — Python WSL-side: directory walk + sample file reads
--   'smart'      — PowerShell Windows-side: SMART attributes via Get-PhysicalDisk
--
-- Each check produces one row. details_json carries the full payload (error
-- lists, per-file timings, SMART counters) so the fixed columns stay lean.

CREATE TABLE IF NOT EXISTS drive_health_checks (
    check_id INTEGER PRIMARY KEY AUTOINCREMENT,
    drive_id INTEGER,
    drive_code TEXT,
    check_date TIMESTAMP NOT NULL,
    mount_point TEXT,
    check_type TEXT NOT NULL,        -- 'read_test' or 'smart'
    total_bytes INTEGER,
    used_bytes INTEGER,
    free_bytes INTEGER,
    files_walked INTEGER,
    unreadable_files INTEGER,
    read_errors INTEGER,
    sample_count INTEGER,
    sample_bytes INTEGER,
    sample_duration_secs REAL,
    avg_read_speed_mbps REAL,
    walk_duration_secs REAL,
    overall_status TEXT,             -- 'healthy', 'degraded', 'failing'
    details_json TEXT,               -- full results including error list, SMART attributes, etc.
    FOREIGN KEY (drive_id) REFERENCES drives(drive_id)
);

CREATE INDEX IF NOT EXISTS idx_health_checks_drive ON drive_health_checks(drive_id);
CREATE INDEX IF NOT EXISTS idx_health_checks_code ON drive_health_checks(drive_code);
CREATE INDEX IF NOT EXISTS idx_health_checks_date ON drive_health_checks(check_date);
CREATE INDEX IF NOT EXISTS idx_health_checks_type ON drive_health_checks(check_type);

-- Record this migration
INSERT INTO schema_migrations (migration_id, applied_at, description)
VALUES (
    '003_add_drive_health_checks',
    datetime('now'),
    'Add drive_health_checks table for pre-reformat health assessment'
);
