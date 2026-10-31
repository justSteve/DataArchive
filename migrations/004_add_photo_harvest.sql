-- Migration: 004_add_photo_harvest
-- Description: Add photo_harvest table for the Photo Description Harvest
-- Created: 2026-10-30
-- Bead: co-06tcu (COO; DataArchive bead store was down at creation)
--
-- One row per unique photo, keyed by its SHA-256 fingerprint, so every copy of
-- a photo on every drive shares one description. source_path is the one
-- readable copy chosen at inventory time.
--
-- status moves through:
--   pending         inventoried, not yet prepared
--   skipped_small   under the size floor (thumbnails, cache files)
--   skipped_path    under a software or system folder (Program Files, AppData,
--                   code repositories, album art); see inventory.SKIP_PATH_PARTS
--   unreadable      missing on disk or not decodable
--   held_sensitive  the local screen flagged it; it is never sent anywhere
--   ready           prepared and screened clean; eligible to send
--   submitted       inside a batch at Anthropic (batch_id set)
--   described       description and tags stored
--   declined        the model declined it; not retried
--   failed          the request errored; eligible for a retry

CREATE TABLE IF NOT EXISTS photo_harvest (
    sha256 TEXT PRIMARY KEY,
    file_id INTEGER,
    drive_code TEXT,
    source_path TEXT NOT NULL,
    size_bytes INTEGER,
    extension TEXT,
    copies INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'pending',
    width INTEGER,
    height INTEGER,
    taken_at TEXT,
    camera TEXT,
    gps_lat REAL,
    gps_lon REAL,
    screen_score REAL,
    screen_classes TEXT,
    batch_id TEXT,
    description TEXT,
    tags_json TEXT,
    people INTEGER,
    setting TEXT,
    text_visible TEXT,
    quality TEXT,
    model_sensitive INTEGER,
    input_tokens INTEGER,
    output_tokens INTEGER,
    error TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_photo_harvest_status ON photo_harvest(status);
CREATE INDEX IF NOT EXISTS idx_photo_harvest_batch ON photo_harvest(batch_id);

INSERT OR IGNORE INTO schema_migrations (migration_id, applied_at, description)
VALUES ('004_add_photo_harvest', datetime('now'), 'Add photo_harvest table for the Photo Description Harvest');
