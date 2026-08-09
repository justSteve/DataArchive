# Adjudication ledger

`adjudications.jsonl` is the durable, git-tracked record of every decision Steve
makes on a memory review packet. One JSON object per line, appended, never
rewritten — the same discipline as `conventions/log.md`. Replaying the file
newest-line-wins reconstructs current state, and a changed mind stays visible as
history rather than overwriting the record of what was thought before.

It exists as a second copy on purpose. `data/` is gitignored in this repo, so the
SQLite store at `data/memory-review/review.db` is local-only. An adjudication is
the one artifact in this pipeline that cannot be regenerated: rebuild the packet
and the same candidates come back, but Steve's ruling on them exists nowhere
else. This is the copy git carries off the box.

Fields: `ts`, `packet_id`, `dedupe_key`, `section`, `anchor_class`, `decision`,
`note`, `decided_at`, `headline`, `source_ref`, `client_id`, `source`.
`decision` is one of `confirm`, `correct`, `discard`, `graduate`, `defer`.

A `graduate` line is a **proposal**, not a write. Promoting a concept into a
knowledge bundle is bead-authorized per `.claude/rules/okf-memory.md`; nothing in
this pipeline can do it.

Runbook: `docs/memory-review-pipeline.md` · bead `da-04r`.
