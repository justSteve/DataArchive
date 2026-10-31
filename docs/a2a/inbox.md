# DataArchive A2A Inbox — append-only event ledger

Every commit a peer agent makes in this repo gets one line here, appended at the
bottom, never edited, in the same commit as the change. Row schema follows
`/root/projects/Strader/docs/a2a/inbox.md`:
`| when | from | kind | bead | memo | paths | note |`

| when | from | kind | bead | memo | paths | note |
|---|---|---|---|---|---|---|
| 2026-10-30 21:40 CT | COO | WRITE | co-06tcu | - | migrations/004_add_photo_harvest.sql, python/photo_harvest/, python/tests/test_photo_harvest.py, python/requirements.txt, docs/photo-harvest.md, docs/a2a/inbox.md | PHOTO DESCRIPTION HARVEST, local stages (Steve, 2026-10-30: COO may write here under DReader's rules). Inventory, prepare (metadata stripped from the sendable copy), local NudeNet screen (held photos never sent, copy deleted). Migration 004 applied to data/archive.db (additive; undo in the runbook). Send stage waits on a funded Anthropic key. 10/10 tests. DataArchive's own bead store was down (Dolt server not running), so the bead is COO's. This ledger is new with this commit. |
