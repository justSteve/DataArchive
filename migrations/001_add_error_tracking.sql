-- Migration: 001_add_error_tracking
-- Description: Add error tracking, task checkpoints, and process monitoring tables
-- Created: 2026-03-04
-- Phase: Production Hardening (Phase 1.4)

-- =================================================
-- PROCESS ERROR TRACKING
-- =================================================

-- Track process-level errors (scan failures, inspection failures, etc.)
CREATE TABLE IF NOT EXISTS process_errors (
    error_id INTEGER PRIMARY KEY AUTOINCREMENT,
    error_type TEXT NOT NULL,              -- 'scan', 'inspection', 'hash_computation', etc.
    process_id TEXT,                       -- scan_id, session_id, etc.
    error_message TEXT NOT NULL,
    error_details TEXT,                    -- JSON with stack trace, context, etc.
    occurred_at TIMESTAMP NOT NULL,
    severity TEXT DEFAULT 'error',         -- 'warning', 'error', 'critical'
    resolved_at TIMESTAMP,
    resolution_notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_process_errors_type ON process_errors(error_type);
CREATE INDEX IF NOT EXISTS idx_process_errors_occurred ON process_errors(occurred_at);
CREATE INDEX IF NOT EXISTS idx_process_errors_unresolved ON process_errors(resolved_at) WHERE resolved_at IS NULL;

-- =================================================
-- OPERATION ERROR TRACKING
-- =================================================

-- Track operation-level errors (database queries, file operations, etc.)
CREATE TABLE IF NOT EXISTS operation_errors (
    operation_error_id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_name TEXT NOT NULL,          -- 'get_scans', 'insert_files_batch', etc.
    operation_type TEXT NOT NULL,          -- 'database', 'filesystem', 'network', etc.
    error_message TEXT NOT NULL,
    error_stack TEXT,                      -- Full stack trace
    context_json TEXT,                     -- JSON with operation parameters
    occurred_at TIMESTAMP NOT NULL,
    retry_count INTEGER DEFAULT 0,
    last_retry_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_operation_errors_name ON operation_errors(operation_name);
CREATE INDEX IF NOT EXISTS idx_operation_errors_type ON operation_errors(operation_type);
CREATE INDEX IF NOT EXISTS idx_operation_errors_occurred ON operation_errors(occurred_at);

-- =================================================
-- TASK CHECKPOINTS
-- =================================================

-- Save state for long-running tasks to enable resumption after crashes
CREATE TABLE IF NOT EXISTS task_checkpoints (
    checkpoint_id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type TEXT NOT NULL,               -- 'scan', 'hash_computation', 'inspection', etc.
    task_id TEXT NOT NULL,                 -- scan_id, session_id, etc.
    checkpoint_name TEXT NOT NULL,         -- 'scan_progress', 'hash_batch_123', etc.
    checkpoint_data TEXT NOT NULL,         -- JSON with state data
    created_at TIMESTAMP NOT NULL,
    last_updated_at TIMESTAMP NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_task_checkpoints_unique ON task_checkpoints(task_type, task_id, checkpoint_name);
CREATE INDEX IF NOT EXISTS idx_task_checkpoints_task ON task_checkpoints(task_type, task_id);
CREATE INDEX IF NOT EXISTS idx_task_checkpoints_updated ON task_checkpoints(last_updated_at);

-- =================================================
-- PROCESS HEARTBEATS
-- =================================================

-- Monitor health of active processes
CREATE TABLE IF NOT EXISTS process_heartbeats (
    heartbeat_id INTEGER PRIMARY KEY AUTOINCREMENT,
    process_type TEXT NOT NULL,            -- 'scan', 'inspection', 'hash_worker', etc.
    process_id TEXT NOT NULL,              -- scan_id, session_id, PID, etc.
    started_at TIMESTAMP NOT NULL,
    last_heartbeat_at TIMESTAMP NOT NULL,
    status TEXT NOT NULL,                  -- 'running', 'idle', 'waiting', 'stalled'
    progress_pct REAL DEFAULT 0.0,
    progress_details TEXT,                 -- JSON with progress info
    host_info TEXT                         -- Hostname, PID, etc.
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_process_heartbeats_unique ON process_heartbeats(process_type, process_id);
CREATE INDEX IF NOT EXISTS idx_process_heartbeats_status ON process_heartbeats(status);
CREATE INDEX IF NOT EXISTS idx_process_heartbeats_last ON process_heartbeats(last_heartbeat_at);

-- =================================================
-- ERROR STATISTICS
-- =================================================

-- Pre-computed error statistics for dashboard display
CREATE TABLE IF NOT EXISTS error_statistics (
    stat_id INTEGER PRIMARY KEY AUTOINCREMENT,
    stat_date DATE NOT NULL,               -- Daily aggregation
    error_type TEXT NOT NULL,
    total_errors INTEGER DEFAULT 0,
    resolved_errors INTEGER DEFAULT 0,
    critical_errors INTEGER DEFAULT 0,
    avg_resolution_time_seconds REAL,
    computed_at TIMESTAMP NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_error_stats_unique ON error_statistics(stat_date, error_type);
CREATE INDEX IF NOT EXISTS idx_error_stats_date ON error_statistics(stat_date);

-- =================================================
-- SCHEMA VERSION TRACKING
-- =================================================

-- Track which migrations have been applied
CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_id TEXT PRIMARY KEY,
    applied_at TIMESTAMP NOT NULL,
    description TEXT
);

-- Record this migration
INSERT INTO schema_migrations (migration_id, applied_at, description)
VALUES (
    '001_add_error_tracking',
    datetime('now'),
    'Add error tracking, task checkpoints, and process monitoring tables'
);
