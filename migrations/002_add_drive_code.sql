-- Migration: 002_add_drive_code
-- Description: Add drive_code column to drives table
-- Created: 2026-05-02
-- Bead: da-7pq
--
-- drive_code is a short mnemonic label (e.g. "WHYD", "RRTI") assigned by the
-- operator during scanning. It was originally added to production via ad-hoc
-- ALTER TABLE; this migration formalizes it as part of the managed schema.
--
-- Idempotency note: The ALTER TABLE will fail with "duplicate column name" if
-- the column already exists (production DB). The migration runner handles this
-- by catching the error and recording the migration as applied anyway.

ALTER TABLE drives ADD COLUMN drive_code TEXT;

-- Record this migration
INSERT INTO schema_migrations (migration_id, applied_at, description)
VALUES (
    '002_add_drive_code',
    datetime('now'),
    'Add drive_code column to drives table'
);
