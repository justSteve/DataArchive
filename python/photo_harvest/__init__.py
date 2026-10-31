"""Photo Description Harvest. [co-06tcu]

Gives every unique catalogued photo a one-sentence description and tags from
Claude Haiku, sent through Anthropic's Message Batches API. Results live in
archive.db's photo_harvest table, keyed by SHA-256, so every copy of a photo
shares one description.

Stages, each resumable from the table's status column:
  inventory  one row per unique fingerprint, one readable copy chosen
  prepare    upright, HEIC to JPEG, long side <= 1568 px, all metadata stripped;
             the photo's own date, camera and location are kept locally
  screen     a local NudeNet pass; anything flagged is held_sensitive and is
             never sent anywhere
  send       (needs a funded Anthropic key) batches of ready photos

Originals are only ever read. Prepared copies are temporary.

Plan: /root/projects/COO/myDesk/reports/photo-description-harvest-plan.md
Delegated from COO bead co-06tcu (Steve, 2026-10-30).
"""

__version__ = "0.1.0"
