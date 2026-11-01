# Photo Description Harvest — Runbook

*Delegated from COO bead co-06tcu (Steve, 2026-10-30). Plan:
`/root/projects/COO/myDesk/reports/photo-description-harvest-plan.md`.*

Gives every unique catalogued photo a one-sentence description and tags from
Claude Haiku 5.5 through Anthropic's Message Batches API. Results go in
`data/archive.db`, table `photo_harvest`, one row per SHA-256.

## What never leaves this machine

- Any photo the local screen holds (`held_sensitive`). Its prepared copy is
  deleted the moment it is flagged, so no sendable copy exists.
- The photo's own date, camera and GPS location. They are read from the
  original into the table; the copy that is sent has no metadata at all.
- Originals are only read, never changed or moved.

## Stages

Run from `DataArchive/python` with its venv:

```bash
cd /root/projects/DataArchive/python
.venv/bin/python -m photo_harvest inventory            # add new fingerprints
.venv/bin/python -m photo_harvest inventory --recheck  # look again for unreadable ones
.venv/bin/python -m photo_harvest prepare --limit 500  # prepare + local screen
.venv/bin/python -m photo_harvest status               # counts by status
.venv/bin/python -m photo_harvest held                 # held photos, by location only
```

Every stage resumes from `status`; Ctrl+C is safe between photos.

```bash
.venv/bin/python -m photo_harvest check                 # one tiny request: key and credit
.venv/bin/python -m photo_harvest send --size 500       # one batch: submit, wait, store, delete
.venv/bin/python -m photo_harvest collect <batch id>    # finish a batch after an interruption
.venv/bin/python -m photo_harvest page                  # desk page of described photos
```

The key is `ANTHROPIC_API_KEY` in `/home/vault/DataArchive/env` (written with
`COO/factory/scripts/vault-set.py DataArchive ANTHROPIC_API_KEY`), read into
memory only. Spending is paid from the Max plan's monthly API credits. `send`
refuses a batch that could take total spend past `--budget` (default $20),
counted from the token totals on stored results. Each batch is deleted from
Anthropic's service once its results are stored. If `send` is interrupted
after submitting, rows stay `submitted` with their `batch_id`; run `collect`.

### Unattended full run

```bash
systemd-run --unit=photo-harvest-run --working-directory=/root/projects/DataArchive/python \
  /root/projects/DataArchive/python/.venv/bin/python -m photo_harvest run --chunk 300 --budget 20
journalctl -u photo-harvest-run -f          # watch
cat /var/moo/photo-harvest/progress.json   # state, counts, spend
systemctl stop photo-harvest-run           # stop; re-launch resumes
```

### Where copies are looked for

`/mnt/z/Harvest/<drive_code>/<path>`, then each alternate root
(`PHOTO_HARVEST_ALT_ROOTS`, default `/mnt/f:/mnt/w`), then wherever
`Harvester/manifests/harvest-<drive_code>.jsonl` says the copy went.

### Status values

See `migrations/004_add_photo_harvest.sql`. `skipped_path` covers software and
system folders (`inventory.SKIP_PATH_PARTS`); a photo is skipped only when every
copy of it would be.

## Settings

All in `photo_harvest/config.py`, each overridable by environment variable:
database, roots, work folder (`/var/moo/photo-harvest/work`), size floor
(20 KB, 200 px), long side 1568 px, screen threshold 0.25 (low on purpose).

## Tests

```bash
cd /root/projects/DataArchive && PYTHONPATH=python python/.venv/bin/python -m unittest python/tests/test_photo_harvest.py -v
```

## Undo

`DROP TABLE photo_harvest; DELETE FROM schema_migrations WHERE migration_id='004_add_photo_harvest';`
and `rm -r /var/moo/photo-harvest`. Nothing else in the catalog is touched.

## Findings from the first inventory (2026-10-30)

- 30,570 unique photos. (The first count, 33,830, double-counted 3,260
  photos the catalog stores under both an upper- and a lower-case fingerprint;
  merged 2026-10-31, backup in /var/moo/photo-harvest/backups/.)
- About 5,200 of the not-found are Tera1A `PicasaRoot` (including Moms Scans).
  The Tera1A manifest records them copied to `F:\Tera1A\PicasaRoot`, which does
  not exist on F: or Z: today.
- 71 SVNK OneDrive photos were catalogued and harvested as all-zero files
  (cloud placeholders). The catalog hash is of the zeros. At least one has a
  real copy elsewhere under a different hash (RRTI, Picasa Backup - All Moms
  Scanned Photos).
