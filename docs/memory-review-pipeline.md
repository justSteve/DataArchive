# Memory Review Pipeline — Operator Runbook

**Bead:** da-04r (Memory Review Pipeline) · delegated from COO `co-85xyp`
**Design context:** `/root/projects/COO/docs/specs/graduation-trigger-design.md` and its addendum
**Status:** built and exercised against the live corpus, 2026-08-09

---

## What it is

A cron-driven pipeline that reads Claude Monitor's conversation corpus and the
local memory tiers, pre-processes them into a **review packet**, publishes that
packet as an **interactive desk page**, and records Steve's decisions in a
durable store — without him retyping anything into chat.

The one thing to understand before reading further: **the pipeline proposes, it
never writes shared truth.** No code path in it can write to `conventions/`,
`Strader/knowledge/`, `conventions/log.md`, or any `.claude/rules/` file. Bundle
writes are bead-authorized per `.claude/rules/okf-memory.md`. A "graduate" ruling
here produces a proposal for a bead, nothing more.

## Why it exists

Adjudication cannot be automated. A similarity score reads *"center the fly on
the consolidation range"* and *"never center a fly on a range"* as a near-identical
pair, because they share a subject — they are opposites. Detection automates to a
candidate list; only a reader separates agreement from contradiction.

The packet exists to put that reader in front of the right list while the
conversations are still fresh, and to flag **COO's inferences separately from
things Steve actually said** — because a wrong inference, left alone, hardens into
curated truth and starts outranking correct concepts. The worked example is the
butterfly case (`co-0a3oj`): a wrong framing in an always-loaded file produced a
month of confidently wrong work and five hand-corrections, while every automatic
surface reported success.

---

## The five sections of a packet

| Section | What it holds | Who rules on it |
|---|---|---|
| **Contradictions** | a memory or concept colliding with a file loaded into EVERY session | Steve — the machine cannot tell which side is wrong |
| **New memories** | cards and concepts written since the last completed review | Steve |
| **Collisions** | a new memory landing on top of an existing curated concept | Steve |
| **Graduation candidates** | things said ≥3 times, in ≥3 sessions, across ≥3 days, that no concept covers | Steve |
| **Stated vs. inferred** | not a section — a badge on every item | the evidence is shown so the badge can be overruled on sight |

Contradictions are listed first deliberately. A wrong loaded instruction actively
produces wrong work; a missing concept merely fails to help.

### What "Steve stated this" means, precisely

It means a verbatim utterance in the corpus shares enough **rare** vocabulary
with the memory to be shown as its anchor, and the packet displays that quote
with its date and match strength. It is a claim about *evidence*, not about
truth. "COO inference" means no such utterance was found — which does not make
the memory wrong, only unverified.

The anchor test is deliberately strict, because a false "stated" is the expensive
error: it lets an unverified inference pass unflagged, which is the failure this
whole pipeline exists to catch. A false "inference" costs a glance.

---

## Daily operation

Nothing needs doing. Three cron entries carry it:

```cron
# Daily collection + packet build + desk page refresh (23:15, after COO's 22:30 zepo pulse)
15 23 * * *  /usr/bin/bash /root/projects/DataArchive/scripts/cron/memory-review-daily.sh

# Capture endpoint supervisor — restarts it if it is not listening
*/5 * * * *  /usr/bin/bash /root/projects/DataArchive/scripts/cron/memory-review-endpoint.sh supervise

# The weekly sitting: refresh, ensure the endpoint, open the page (Friday 16:30)
30 16 * * 5  /usr/bin/bash /root/projects/DataArchive/scripts/cron/memory-review-weekly.sh
```

Install them with `crontab -e`, or apply the file:

```bash
crontab -l > /tmp/current && cat /root/projects/DataArchive/scripts/cron/crontab.memory-review.txt >> /tmp/current && crontab /tmp/current
```

## On demand

```bash
cd /root/projects/DataArchive
export PYTHONPATH=python

python3 -m memory_review status          # what ran, when, and is it healthy
python3 -m memory_review collect         # pull CM + the local memory tiers now
python3 -m memory_review publish         # rebuild the packet and the desk page
python3 -m memory_review traffic         # what this pipeline asked CM, and got back
python3 -m memory_review config          # effective config and discovered inputs
```

`-v` before the subcommand prints passing assertions as well as failures:
`python3 -m memory_review -v collect`.

## Where things live

| Thing | Path |
|---|---|
| The page Steve opens | `file://wsl.localhost/Zgent/var/moo/desk/desk-memory-review.html` |
| The same page, served | `http://127.0.0.1:3010/review` |
| Operational store | `data/memory-review/review.db` (gitignored, per repo convention) |
| **Durable adjudication record** | `memory-review/ledger/adjudications.jsonl` (tracked, append-only) |
| CM traffic, per request | `/var/moo/logs/memory-review/cm-traffic-<date>.jsonl` |
| Run logs | `/var/moo/logs/memory-review/daily-<date>.log`, `weekly-<date>.log`, `endpoint.log` |
| Heartbeats | `/var/moo/state/memory-review-{collect,packet,endpoint}-heartbeat.json` |
| Code | `python/memory_review/` |
| Tests | `python/tests/test_memory_review.py` |

The desk page path is a **bookmark contract** — Steve parks a tab on it and
refreshes in place. Do not move it (`tmuxMOO/bin/desk-html.sh` header, `co-gsbnb`).

---

## How Steve's decisions get captured

Each item on the page carries five choices and a free-text note:

| Choice | Meaning |
|---|---|
| **Confirm** | right as written; leave it alone |
| **Correct** | nearly right, or wrongly framed — the note carries the correction |
| **Discard** | wrong; tombstone it so it stops coming back (**a reason is required**) |
| **Graduate** | worth promoting into curated truth — files a proposal, never a write |
| **Defer** | not now; it returns in the next packet |

The capture path, in order of what survives what:

1. **Every keystroke autosaves to the browser** (`localStorage`, keyed by packet
   id). Closing the tab, a reboot, or a dead endpoint loses nothing; reopening
   the page restores every answer and note.
2. **"Record my decisions" POSTs the batch** to `http://127.0.0.1:3010/api/adjudications`.
   A 200 means the row is in SQLite **and** the line is fsynced to the
   git-tracked ledger. Anything else is reported in red with the exact reason.
3. **If the endpoint is unreachable**, the page says so in a red panel, keeps the
   answers, and offers **Download as file**. Import it later with:
   ```bash
   cd /root/projects/DataArchive
   PYTHONPATH=python python3 -m memory_review import ~/Downloads/memory-review-decisions.json
   ```
4. The connection pill at the top of the page probes the endpoint on load, so the
   state is visible before any work is done rather than after.

Submitting part of a packet does **not** advance the review window. The window
moves only when every item has been ruled on; until then the unanswered items
come back in the next packet.

---

## How a failure announces itself

This is the part that matters most, and it is built against a specific history:
in one day this enterprise surfaced six defects of the same shape — work fails
and every automatic surface reports green.

**A run that found nothing is not a run that never happened.** Every run writes a
heartbeat carrying the inputs it examined, so `candidates: 0` alongside
`memory_files_seen: 275` reads as a healthy empty pass, while a missing file or
an old `ts` reads as a miss:

```bash
python3 -m memory_review status
```

```
MEMORY REVIEW: OK
  collect   ok         41s ago
  packet    ok         38s ago
  endpoint  ok         12s ago
  packet     #7 · ok · 71 items · built 2026-08-09T19:40:46Z
  corpus     927 utterances collected
  cm traffic 662 requests, 2 failed, 37625457 bytes
  ledger     14 adjudications across 2 packet(s) {'confirm': 9, 'correct': 3, 'discard': 2}
```

States are distinct: `ok`, `degraded`, `failed`, `stale` (it stopped firing),
`missing` (it has never run, or cannot write its state), `unreadable`. An
unrecognised status is treated as **failed** — every status branch fails closed.

**Input assertions, checked before any result is trusted:**

| Assertion | On failure |
|---|---|
| CM reachable | `failed` · exit 2 · **cursor not advanced** |
| CM corpus fresh (< 24h) | `degraded` · no CM pull · **cursor not advanced** |
| CM ingest scheduler last run succeeded | `degraded`, with the reported status |
| instruction surfaces / memory dirs / bundles found | `failed` — an empty layout means the box moved |
| conversations returned but zero entries | `degraded` — an answering-but-empty endpoint |
| last collection healthy | packet built anyway, marked `degraded`, **banner on the page** |
| similarity backend healthy | `failed` |

**Not advancing the cursor on a bad run is the point:** the skipped window is
re-read once the dependency recovers, instead of being silently lost. That exact
pattern cost this enterprise twenty days of MemPalace ingest.

Exit codes are uniform: **0 healthy · 1 degraded · 2 failed**.

A degraded packet still publishes, carrying a red banner naming its degradation.
Publishing nothing on a bad day is how a pipeline goes quiet without anyone
noticing.

### The CM traffic log

Every request this pipeline makes to Claude Monitor is recorded — endpoint,
parameters, status, duration, bytes, row count — in SQLite and mirrored to
`/var/moo/logs/memory-review/cm-traffic-<date>.jsonl`.

```bash
python3 -m memory_review traffic --limit 20
python3 -m memory_review traffic --json | jq '.summary'
```

This is a purpose, not a side effect: the gaps in what CM can answer are only
findable if the asking is written down. A gap in the log means the process died —
a different diagnosis from a logged 500.

---

## Diagnosing the common failures

**"The page says the capture endpoint is unreachable."**
```bash
bash scripts/cron/memory-review-endpoint.sh status
bash scripts/cron/memory-review-endpoint.sh start
tail -40 /var/moo/logs/memory-review/endpoint.log
```
Answers are safe in the browser meanwhile. The `*/5` supervisor cron normally
restarts it within five minutes.

**"`status` says collect is stale."** The cron did not fire, or it failed before
writing. Check `/var/moo/logs/memory-review/daily-<date>.log`, then `crontab -l`.

**"Collect reports degraded: corpus stale."** CM stopped ingesting. Check
`curl -s localhost:3002/api/v1/health | jq .scheduler`. The pipeline is behaving
correctly by refusing to cluster a frozen corpus.

**"The packet is empty."** Read the counters, not the item count. `memory_files_seen`
and `utterances_scanned_for_graduation` non-zero with `items_total: 0` is a real
empty result — nothing changed and nothing collided. `memory_files_seen: 0` is a
failure and will already have failed an assertion.

**"A section is full of near-duplicates."** Report it. The collision leg already
drops pairs at or above `MR_TAU_IDENTICAL` (0.70) and the contradiction leg folds
identical passages deployed across repos into one row; a new duplicate shape means
a threshold needs retuning.

---

## Tuning

Every threshold is an environment variable, and every one is recorded in the
heartbeat and in each packet, so a packet's contents are always attributable to
the thresholds that produced them. They were set from the measured score
distribution of the live corpus on 2026-08-09 — sitting just above the 99th
percentile of unrelated pairs — not chosen by taste:

| Comparison | Pairs measured | median | p99 | max | Threshold in force |
|---|---|---|---|---|---|
| concept ↔ concept | 35,153 | 0.041 | 0.157 | 1.000 | `MR_TAU_COLLIDE=0.25` |
| concept ↔ loaded instruction | 43,847 | 0.042 | 0.135 | 0.583 | `MR_TAU_INSTRUCTION=0.15` |
| utterance ↔ utterance | 4,645 | 0.056 | 0.354 | 1.000 | `MR_TAU_CLUSTER=0.35` |

Others: `MR_TAU_ANCHOR`, `MR_ANCHOR_MIN_SHARED`, `MR_ANCHOR_MIN_RARITY`,
`MR_TAU_IDENTICAL`, `MR_TAU_DISMISS`, `MR_MAX_*` caps, `MR_UTTERANCE_MIN/MAX`.
`python3 -m memory_review config` prints the effective set.

Re-measure after any corpus change:

```bash
PYTHONPATH=python python3 - <<'PY'
from memory_review.store import Store
from memory_review import similarity as S
import statistics
s = Store(); concepts = s.memory_items(kind="okf-concept")
texts = ["\n".join(filter(None,[c["title"], c["description"], c["body"]])) for c in concepts]
voc = S.Vocabulary(texts); tok = [S.content_tokens(t) for t in texts]
vals = [voc.score(tok[i], tok[j], 4)[0]
        for i in range(len(tok)) for j in range(i+1, len(tok))
        if len(tok[i] & tok[j]) >= 4]
print("median %.3f p99 %.3f max %.3f" % (
    statistics.median(vals), statistics.quantiles(vals, n=100)[98], max(vals)))
PY
```

## Lifecycle

| Event | Behaviour |
|---|---|
| **Reboot** | the `*/5` supervisor restarts the endpoint; the daily cron picks up at 23:15; the cursor was never advanced past unread work |
| **First run on a fresh store** | every memory reads as "new" — a bootstrap artifact, capped at `MR_MAX_NEW_MEMORIES` (40). Rule on them or Defer; the rest return next packet |
| **CM down for days** | collect fails loudly each night, cursor held, window re-read in full on recovery |
| **Store lost** | rebuild with `collect --since <date>`; adjudications are recovered from the tracked ledger (`ledger.replay()`) |
| **Endpoint stopped** | its heartbeat goes stale within 15 minutes; the page reports unreachable and holds answers locally |
| **Thresholds retuned** | old packets keep the thresholds they were built with, recorded in `packets.thresholds_json` |

## Tests

```bash
cd /root/projects/DataArchive
PYTHONPATH=python python3 -m unittest discover -s python/tests -p "test_memory_review.py" -v
```

76 tests. They cover the extraction filter (what counts as Steve speaking), the
fail-closed status branches, the strike rule, anchor classification, adjudication
idempotency, the CM pagination walk, the injection defence on the embedded packet,
and — functionally, by hashing every file before and after a full build — that no
code path writes into a knowledge bundle.

## Class

DataArchive is a **service**, not a zgent. This pipeline adds no ritual skills and
no ritual permission grants, and the class check must keep passing:

```bash
bash /root/projects/COO/factory/scripts/check-member-class.sh DataArchive
```

## Known limits — stated plainly

1. **The anchor test is lexical.** It finds shared rare vocabulary, not shared
   meaning. A restatement in entirely different words reads as an inference. The
   `SimilarityIndex` interface exists so a vector backend can replace it when
   `co-ta0m` settles; `backend_name()` is in every heartbeat so an A/B is a query.
2. **Extraction precision was measured by hand on two samples** (30 rows, then 25
   rows) drawn from a 30-day window, at 90% and 96% respectively; every failure
   found was harness scaffolding, and each was added to the filter. It has not
   been measured since the last filter additions, and recall was never measured
   at all — utterances the filter wrongly drops are invisible by construction.
3. **The graduation section will often be empty.** One person's utterances rarely
   repeat three times across three sessions and three days. That is an honest
   result, not a fault, but it means the section's value is unproven.
4. **Contradiction detection finds topic collisions, not contradictions.** Naming
   which side is wrong needs a reader, always. The deterministic
   `contradicts_if_present` leg is exact but only covers concepts whose authors
   declared phrases — currently almost none.
5. **The weekly cadence is chosen, not measured.** It comes from a single observed
   latency (roughly four weeks, once, in the butterfly case).
