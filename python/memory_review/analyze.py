"""Packet build: turn the collected corpus into a list a reader can act on. [da-04r]

Five sections, in the order Steve reads them:

  1. `new_memory`            — what got written into a memory tier since the last review
  2. `collision`             — a new memory that lands on top of an existing curated concept
  3. `contradiction`         — a memory or concept that collides with an ALWAYS-LOADED instruction
  4. `graduation_candidate`  — a thing Steve has said repeatedly that no concept covers
  5. the split that runs through all of them — **Steve stated it** vs **COO inferred it**

Section 5 is not a section, it is a property of every item, and it is the point of
the whole exercise. An item is `steve_stated` only when a verbatim utterance from
the corpus supports it, and the packet shows that utterance with its date. An item
with no verbatim anchor is `coo_inference` — COO wrote it down, and nobody said it.
That label is a claim about *evidence*, not about truth: an inference can be
perfectly correct. It is flagged because a wrong one, left alone, hardens into
curated truth and starts outranking correct concepts, and the butterfly case
(co-0a3oj) is what that costs — a wrong framing in an always-loaded file produced
a month of confidently wrong work and five hand-corrections.

What this module will not do: decide. Similarity finds *aboutness*; it scores
"center the fly on the consolidation range" and "never center on a range" as a
near-identical pair because they share a subject. Only a reader separates
agreement from contradiction. Every output here is a candidate for that reader.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Sequence

from . import config, extract, heartbeat, similarity
from .store import Store, utcnow

SECTION_NEW = "new_memory"
SECTION_COLLISION = "collision"
SECTION_CONTRADICTION = "contradiction"
SECTION_GRADUATION = "graduation_candidate"

ANCHOR_STATED = "steve_stated"
ANCHOR_INFERENCE = "coo_inference"
ANCHOR_NA = "not_applicable"

LAST_REVIEW_CURSOR = "last_review_at"


class _NoInputs(RuntimeError):
    """Nothing to build from. Distinct from 'built and found nothing'."""


def _key(*parts: str) -> str:
    """Stable dedupe key. Survives a rebuild, so an answered item stays answered."""
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return digest[:24]


def _short(text: str, limit: int = 240) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _repo_of(path: str) -> str:
    parts = Path(path).parts
    if "projects" in parts:
        idx = parts.index("projects")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return Path(path).parent.name


# --- anchoring ----------------------------------------------------------------

class UtteranceCorpus:
    """Steve's verbatim words, with an IDF vocabulary built from them.

    Deliberately not a `LexicalIndex`: anchoring asks a different question from
    topic search — "did he say this", not "is this about the same thing" — and it
    needs the rare-word mass floor argued in `similarity.anchor_score`.
    """

    def __init__(self, utterances: Sequence[sqlite3.Row]):
        self.rows = list(utterances)
        self.texts = [r["content"] for r in self.rows]
        self.vocabulary = similarity.Vocabulary(self.texts)

    def __len__(self) -> int:
        return len(self.rows)

    def best(self, text: str, k: int, threshold: float,
             min_shared: int, min_mass: float
             ) -> list[tuple[float, int, float, sqlite3.Row]]:
        scored: list[tuple[float, int, float, sqlite3.Row]] = []
        for row in self.rows:
            score, shared, mass = similarity.anchor_score(
                text, row["content"], vocabulary=self.vocabulary,
                min_shared_tokens=min_shared, min_shared_rarity=min_mass)
            if score >= threshold and score > 0:
                scored.append((score, shared, mass, row))
        scored.sort(key=lambda item: (item[2], item[0]), reverse=True)
        return scored[:k]


def build_utterance_index(utterances: Sequence[sqlite3.Row]) -> UtteranceCorpus:
    return UtteranceCorpus(utterances)


def classify_anchor(text: str, corpus: "UtteranceCorpus",
                    threshold: float | None = None, k: int = 3
                    ) -> tuple[str, list[dict]]:
    """Did Steve actually say this, or did COO infer it?

    Returns `(anchor_class, evidence)`. Evidence is up to `k` verbatim utterances
    with their date, the count of distinctive words shared, and the rare-word
    mass behind the match — so the reader judges the anchor instead of trusting a
    score. A weak anchor shown next to its claim is self-refuting on sight; a
    hidden one is not.
    """
    threshold = config.TAU_ANCHOR if threshold is None else threshold
    if not isinstance(corpus, UtteranceCorpus) or not len(corpus):
        return ANCHOR_INFERENCE, []
    hits = corpus.best(text, k=k, threshold=threshold,
                       min_shared=config.ANCHOR_MIN_SHARED_TOKENS,
                       min_mass=config.ANCHOR_MIN_SHARED_RARITY)
    if not hits:
        return ANCHOR_INFERENCE, []
    evidence = [{
        "quote": _short(row["content"], 400),
        "ts": row["ts"],
        "day": row["day"],
        "project": row["project"],
        "score": round(score, 3),
        "shared_words": shared,
        "rare_word_score": round(mass, 1),
    } for score, shared, mass, row in hits]
    return ANCHOR_STATED, evidence


# --- sections -----------------------------------------------------------------

def section_new_memories(store: Store, window_from: str,
                         utterance_index: UtteranceCorpus,
                         limit: int) -> list[dict]:
    """Memory cards and concepts written or changed inside the review window."""
    rows = store.memory_items_changed_since(window_from)
    items: list[dict] = []
    for row in rows[:limit]:
        text = "\n".join(filter(None, [row["title"], row["description"], row["body"]]))
        anchor, evidence = classify_anchor(text, utterance_index)
        items.append({
            "section": SECTION_NEW,
            "dedupe_key": _key(SECTION_NEW, row["item_key"], row["body_hash"]),
            "anchor_class": anchor,
            "headline": row["title"] or Path(row["source_path"]).stem,
            "body": _short(row["description"] or row["body"], 700),
            "source_ref": row["source_path"],
            "score": None,
            "evidence": {
                "kind": row["kind"],
                "repo": row["repo"],
                "changed_at": row["changed_at"],
                "first_seen_at": row["first_seen_at"],
                "is_new": row["first_seen_at"] == row["changed_at"],
                "anchors": evidence,
                "full_body": _short(row["body"], 2000),
            },
        })
    return items


def section_collisions(store: Store, new_rows: Sequence[sqlite3.Row],
                       concept_index: similarity.LexicalIndex,
                       limit: int, stats: dict | None = None) -> list[dict]:
    """A new memory that lands on top of an existing curated concept.

    Three readings, and the packet does not choose between them — that is the
    reader's job:
      * the concept already says this (the memory is redundant),
      * the concept says the opposite (a contradiction wearing a similarity score),
      * the concept is badly worded or unfindable, which is why it got restated.
    """
    items: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()
    for row in new_rows:
        text = "\n".join(filter(None, [row["title"], row["description"], row["body"]]))
        if stats is not None:
            duplicates = concept_index.query(
                text, k=3, threshold=config.TAU_IDENTICAL,
                exclude=[row["item_key"]])
            stats["suppressed_as_duplicate"] = (
                stats.get("suppressed_as_duplicate", 0) + len(duplicates))
        hits = concept_index.query(text, k=3, threshold=config.TAU_COLLIDE,
                                   exclude=[row["item_key"]],
                                   max_score=config.TAU_IDENTICAL)
        for key, score, meta in hits:
            # A ↔ B and B ↔ A are one finding. Both appear because every changed
            # item is queried against every concept, and showing the reader the
            # same pair twice halves the useful size of a capped section.
            pair = tuple(sorted((row["item_key"], key)))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            items.append({
                "section": SECTION_COLLISION,
                "dedupe_key": _key(SECTION_COLLISION, row["item_key"], key),
                "anchor_class": ANCHOR_NA,
                "headline": f"{row['title'] or Path(row['source_path']).stem} "
                            f"↔ {meta.get('title') or Path(key).stem}",
                "body": _short(row["description"] or row["body"], 500),
                "source_ref": row["source_path"],
                "score": round(score, 3),
                "evidence": {
                    "new_item": {
                        "title": row["title"], "path": row["source_path"],
                        "kind": row["kind"], "text": _short(row["body"], 1200),
                    },
                    "existing_concept": {
                        "title": meta.get("title"), "path": meta.get("path"),
                        "repo": meta.get("repo"),
                        "text": _short(meta.get("text", ""), 1200),
                    },
                    "similarity": round(score, 3),
                    "caveat": "Similarity measures subject overlap only. A high "
                              "score is equally consistent with agreement and with "
                              "the exact opposite claim.",
                },
            })
    items.sort(key=lambda item: item["score"] or 0, reverse=True)
    return items[:limit]


def section_contradictions(store: Store,
                           memory_rows: Sequence[sqlite3.Row],
                           instruction_index: similarity.LexicalIndex,
                           passages: Sequence[extract.Passage],
                           limit: int) -> list[dict]:
    """Collisions against files that are loaded into every session.

    This section outranks the others in consequence. A retrieved memory has to
    win a race to be seen; an always-loaded instruction is simply present. A
    wrong loaded instruction actively produces wrong work, while a missing
    concept merely fails to help.

    Two legs:
      * topic collision, ranked and capped (needs a reader);
      * `contradicts_if_present` frontmatter phrases, exact and deterministic,
        with negated and quoted lines excluded so a stated prohibition is not
        reported as the violation.
    """
    items: list[dict] = []

    # Leg A′ — deterministic banned phrases, highest confidence, listed first.
    for row in memory_rows:
        try:
            front = json.loads(row["frontmatter_json"] or "{}")
        except ValueError:
            front = {}
        declared = front.get("contradicts_if_present") or []
        if isinstance(declared, str):
            declared = [declared]
        if not declared:
            continue
        for hit in extract.find_banned_phrases(declared, passages):
            items.append({
                "section": SECTION_CONTRADICTION,
                "dedupe_key": _key(SECTION_CONTRADICTION, "banned", row["item_key"],
                                   hit["path"], str(hit["line"]), hit["phrase"]),
                "anchor_class": ANCHOR_NA,
                "headline": f"BANNED PHRASE “{hit['phrase']}” in {Path(hit['path']).name}"
                            f":{hit['line']}",
                "body": hit["text"],
                "source_ref": f"{hit['path']}#L{hit['line']}",
                "score": 1.0,
                "evidence": {
                    "leg": "deterministic",
                    "concept": {"title": row["title"], "path": row["source_path"]},
                    "instruction": hit,
                    "why": "This concept declares the phrase as one that must never "
                           "appear in a loaded instruction, and it appears in one.",
                },
            })

    # Leg A — topic collision against the loaded surface.
    #
    # Deduped by (concept, passage TEXT), not by path: the same rule file is
    # deployed to eighteen repos, and eighteen rows saying the same thing would
    # fill the cap and hide every other finding. The repos carrying the passage
    # are listed on the one row instead — which also makes a repo that carries a
    # STALE copy visible as its own row, because its text differs.
    scored: list[dict] = []
    seen_passage: dict[str, dict] = {}
    for row in memory_rows:
        text = "\n".join(filter(None, [row["title"], row["description"], row["body"]]))
        hits = instruction_index.query(text, k=3, threshold=config.TAU_INSTRUCTION)
        for key, score, meta in hits:
            fold_key = f"{row['item_key']}|{meta.get('text_hash')}"
            if fold_key in seen_passage:
                repos = seen_passage[fold_key]["evidence"]["instruction"]["also_in"]
                if meta.get("repo") not in repos:
                    repos.append(meta.get("repo"))
                continue
            candidate = {
                "section": SECTION_CONTRADICTION,
                "dedupe_key": _key(SECTION_CONTRADICTION, "topic", row["item_key"], key),
                "anchor_class": ANCHOR_NA,
                "headline": f"{row['title'] or Path(row['source_path']).stem} "
                            f"↔ {meta.get('repo')}/"
                            f"{Path(meta.get('path','')).name}"
                            f":{meta.get('start_line')}",
                "body": _short(meta.get("text", ""), 600),
                "source_ref": f"{meta.get('path')}#L{meta.get('start_line')}-"
                              f"{meta.get('end_line')}",
                "score": round(score, 3),
                "evidence": {
                    "leg": "topic-collision",
                    "concept": {
                        "title": row["title"], "path": row["source_path"],
                        "kind": row["kind"], "text": _short(row["body"], 1200),
                    },
                    "instruction": {
                        "repo": meta.get("repo"), "path": meta.get("path"),
                        "heading": meta.get("heading"),
                        "lines": f"{meta.get('start_line')}-{meta.get('end_line')}",
                        "text": _short(meta.get("text", ""), 1200),
                    },
                    "similarity": round(score, 3),
                    "caveat": "Same subject, unknown polarity. The instruction may "
                              "agree, contradict, or merely overlap — and when they "
                              "disagree the instruction is not automatically the "
                              "error. Only a reader can rule on which side is wrong.",
                },
            }
            candidate["evidence"]["instruction"]["also_in"] = [meta.get("repo")]
            seen_passage[fold_key] = candidate
            scored.append(candidate)
    scored.sort(key=lambda item: item["score"] or 0, reverse=True)
    items.extend(scored[:max(0, limit - len(items))])
    return items[:limit]


def section_graduation(store: Store, utterances: Sequence[sqlite3.Row],
                       concept_index: similarity.LexicalIndex,
                       limit: int) -> tuple[list[dict], dict]:
    """Things Steve has said repeatedly that no curated concept covers.

    The 3-strike rule is unchanged from the ratified April design: at least three
    occurrences, across at least three distinct sessions, spanning at least three
    days. Tombstoned clusters are suppressed and the suppression is counted, so a
    rejected idea staying rejected is visible rather than a silent black hole.
    """
    stats = {"clusters": 0, "struck": 0, "suppressed_by_tombstone": 0,
             "already_covered": 0}
    if not utterances:
        return [], stats

    pairs = [(str(row["id"]), row["content"]) for row in utterances]
    by_id = {str(row["id"]): row for row in utterances}
    vocabulary = similarity.Vocabulary(text for _, text in pairs)
    clusters = similarity.cluster(pairs, config.TAU_CLUSTER, vocabulary=vocabulary)
    stats["clusters"] = len(clusters)

    tombstones = store.active_tombstones()
    tombstone_index = similarity.LexicalIndex(vocabulary=vocabulary,
                                              min_shared_tokens=3)
    for tomb in tombstones:
        tombstone_index.add(str(tomb["id"]), tomb["centroid_text"],
                            {"reason": tomb["reason"], "created_at": tomb["created_at"]})

    candidates: list[dict] = []
    for member_ids in clusters:
        if len(member_ids) < config.STRIKE_MIN_OCCURRENCES:
            continue
        members = [by_id[mid] for mid in member_ids if mid in by_id]
        sessions = {m["cm_conversation_id"] for m in members if m["cm_conversation_id"]}
        days = {m["day"] for m in members if m["day"]}
        if len(sessions) < config.STRIKE_MIN_SESSIONS:
            continue
        if len(days) < config.STRIKE_MIN_DAY_SPREAD:
            continue
        stats["struck"] += 1

        texts = [m["content"] for m in members]
        centroid = similarity.centroid_text(texts, vocabulary=vocabulary)

        suppressed = tombstone_index.query(centroid, k=1, threshold=config.TAU_DISMISS)
        if suppressed:
            stats["suppressed_by_tombstone"] += 1
            store.bump_tombstone(int(suppressed[0][0]))
            continue

        covered = concept_index.query(centroid, k=1, threshold=config.TAU_COLLIDE)
        if covered:
            stats["already_covered"] += 1
            continue

        candidates.append({
            "section": SECTION_GRADUATION,
            "dedupe_key": _key(SECTION_GRADUATION,
                               similarity.normalise(centroid)[:200]),
            "anchor_class": ANCHOR_STATED,  # by construction: it IS Steve's words
            "headline": _short(centroid, 160),
            "body": _short(centroid, 900),
            "source_ref": f"{len(members)} utterances · {len(sessions)} sessions · "
                          f"{len(days)} days",
            "score": float(len(members)),
            "evidence": {
                "occurrences": len(members),
                "sessions": len(sessions),
                "day_spread": len(days),
                "days": sorted(d for d in days if d),
                "anchors": [{
                    "quote": _short(m["content"], 400),
                    "ts": m["ts"], "day": m["day"], "project": m["project"],
                } for m in sorted(members, key=lambda m: m["ts"] or "")[:5]],
                "note": "Every line here is Steve's own text, pulled verbatim from "
                        "the conversation corpus. Nothing in this section is a "
                        "paraphrase.",
            },
        })

    candidates.sort(key=lambda item: item["score"] or 0, reverse=True)
    return candidates[:limit], stats


# --- the pass -----------------------------------------------------------------

def build(store: Store | None = None,
          layout: config.Layout | None = None,
          *,
          window_from: str | None = None,
          write_heartbeat: bool = True,
          heartbeat_path: Path | None = None) -> tuple[int | None, heartbeat.RunReport]:
    """Build one review packet. Returns `(packet_id, report)`.

    A degraded build still publishes — with its degradation stated on the page and
    in the heartbeat. Publishing nothing on a bad day is how a pipeline goes quiet
    without anyone noticing; publishing a banner is how the reader finds out.
    """
    report = heartbeat.RunReport(job="memory-review-packet")
    owns_store = store is None
    store = store or Store()
    layout = layout or config.discover_layout()
    packet_id: int | None = None

    try:
        last_collect = store.last_run("collect")
        report.assert_true(
            "collection_has_run", last_collect is not None,
            "a collection run exists",
            "NO collection run has ever completed — there is nothing to build a "
            "packet from, and an empty packet here would be a lie",
            severity=heartbeat.FAILED)

        if last_collect is None:
            # Return without a packet rather than publishing an empty one. An
            # empty packet at the desk address would read as "reviewed, nothing
            # found" when the truth is "never collected".
            raise _NoInputs("no collection run exists")

        if last_collect is not None:
            collect_status = last_collect["status"]
            if collect_status == heartbeat.OK:
                report.assert_true("last_collection_healthy", True,
                                   "last collection reported ok", "")
            elif collect_status in (heartbeat.DEGRADED, heartbeat.FAILED):
                report.assert_true(
                    "last_collection_healthy", False, "",
                    f"last collection reported {collect_status!r} — this packet is "
                    "built on inputs that are known to be incomplete",
                    severity=heartbeat.DEGRADED, observed=collect_status)
            else:  # fail closed on an unrecognised status
                report.assert_true(
                    "last_collection_healthy", False, "",
                    f"last collection reported unrecognised status "
                    f"{collect_status!r} — treating as failed",
                    severity=heartbeat.FAILED, observed=collect_status)

            report.assert_fresh(
                "collection_recent",
                _parse(last_collect["finished_at"] or last_collect["started_at"]),
                config.COLLECT_STALE_AFTER_SECONDS,
                severity=heartbeat.DEGRADED)

        window_from = (window_from or store.get_cursor(LAST_REVIEW_CURSOR)
                       or _default_window_from())
        window_to = utcnow()

        concepts = store.memory_items(kind="okf-concept")
        auto_memory = store.memory_items(kind="auto-memory")
        passage_rows = store.instruction_passages()
        utterances = store.utterances_since(window_from[:10])

        report.assert_nonempty("okf_concepts_loaded", concepts)
        report.assert_nonempty("instruction_passages_loaded", passage_rows)
        report.assert_nonempty("auto_memory_loaded", auto_memory,
                               severity=heartbeat.DEGRADED)

        concept_index = similarity.LexicalIndex(min_shared_tokens=4)
        for row in concepts:
            concept_index.add(row["item_key"],
                              "\n".join(filter(None, [row["title"], row["description"],
                                                      row["body"]])),
                              {"title": row["title"], "path": row["source_path"],
                               "repo": row["repo"], "text": row["body"]})
        concept_index.fit_vocabulary()

        instruction_index = similarity.LexicalIndex(min_shared_tokens=4)
        passages: list[extract.Passage] = []
        for row in passage_rows:
            passage = extract.Passage(
                repo=row["repo"], path=row["path"], heading=row["heading"],
                start_line=row["start_line"], end_line=row["end_line"],
                text=row["text"], text_hash=row["text_hash"])
            passages.append(passage)
            instruction_index.add(f"{row['path']}#{row['start_line']}", row["text"], {
                "repo": row["repo"], "path": row["path"], "heading": row["heading"],
                "start_line": row["start_line"], "end_line": row["end_line"],
                "text": row["text"], "text_hash": row["text_hash"],
            })
        instruction_index.fit_vocabulary()

        utterance_index = build_utterance_index(utterances)
        report.assert_true(
            "similarity_backend_healthy",
            concept_index.health() == "ok" and instruction_index.health() == "ok",
            f"backend {concept_index.backend_name()} ok",
            "similarity backend reports degraded — it was given nothing to index",
            severity=heartbeat.FAILED)

        changed_rows = store.memory_items_changed_since(window_from)

        items: list[dict] = []
        items += section_new_memories(store, window_from, utterance_index,
                                      config.MAX_NEW_MEMORIES)
        collision_stats: dict = {}
        items += section_collisions(store, changed_rows, concept_index,
                                    config.MAX_COLLISIONS, stats=collision_stats)
        items += section_contradictions(store, list(changed_rows) + list(concepts),
                                        instruction_index, passages,
                                        config.MAX_CONTRADICTIONS)
        # Graduation looks at the WHOLE corpus, not the review window. "Steve
        # keeps saying this" is a corpus-level property: the strike rule already
        # demands a three-day spread, which a seven-day window can barely
        # contain, and a candidate that only strikes on day eight would never be
        # seen. Re-proposing is prevented by the adjudication and tombstone
        # subtractions below, not by the window.
        all_utterances = store.utterances_since()
        graduation, grad_stats = section_graduation(
            store, all_utterances, concept_index, config.MAX_GRADUATION_CANDIDATES)
        report.count("utterances_scanned_for_graduation", len(all_utterances))
        items += graduation

        # Never re-ask a question already answered.
        answered = store.adjudicated_keys()
        before = len(items)
        items = [item for item in items if item["dedupe_key"] not in answered]
        report.count("suppressed_already_adjudicated", before - len(items))

        counts = defaultdict(int)
        for item in items:
            counts[item["section"]] += 1
            counts[f"anchor:{item['anchor_class']}"] += 1

        stats = {
            "sections": dict(counts),
            "graduation": grad_stats,
            "collision": collision_stats,
            "corpus": {
                "utterances_in_window": len(utterances),
                "utterances_total": store.utterance_count(),
                "okf_concepts": len(concepts),
                "auto_memory_cards": len(auto_memory),
                "instruction_passages": len(passage_rows),
                "memory_changed_in_window": len(changed_rows),
            },
            "backend": concept_index.backend_name(),
            "anchor_backend": "idf-token-overlap/2",
        }
        for key, value in stats["corpus"].items():
            report.count(key, value)
        for key, value in counts.items():
            report.count(key, value)
        report.count("items_total", len(items))
        report.count("backend", concept_index.backend_name())

        status = report.status
        degraded_reason = "; ".join(
            a.detail for a in report.failed_assertions) or None

        packet_id = store.create_packet(
            window_from=window_from, window_to=window_to,
            status=status, degraded_reason=degraded_reason,
            thresholds=config.thresholds_snapshot(), stats=stats,
            run_id=last_collect["id"] if last_collect is not None else None)
        store.add_packet_items(packet_id, items)
        report.count("packet_id", packet_id)

    except _NoInputs as exc:
        # Already recorded as a failed assertion; no second note needed.
        report.note(str(exc))
    except Exception as exc:  # noqa: BLE001 — a build failure must be loud
        report.fail(f"{type(exc).__name__}: {exc}")
    finally:
        if write_heartbeat:
            heartbeat.write(
                heartbeat_path or config.PACKET_HEARTBEAT,
                report.as_dict({"packet_id": packet_id}))
        if owns_store:
            store.close()

    return packet_id, report


def mark_reviewed(store: Store, when: str | None = None) -> str:
    """Advance the review window. Called when Steve submits a packet's form."""
    stamp = when or utcnow()
    store.set_cursor(LAST_REVIEW_CURSOR, stamp)
    return stamp


def _default_window_from() -> str:
    start = datetime.now(timezone.utc) - timedelta(days=7)
    return start.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def packet_payload(store: Store, packet_id: int) -> dict:
    """The JSON the desk page embeds and the endpoint serves."""
    packet = store.packet(packet_id)
    if packet is None:
        raise ValueError(f"no packet {packet_id}")
    rows = store.packet_items(packet_id)
    existing = {a["dedupe_key"]: a for a in store.adjudications_for_packet(packet_id)}

    items = []
    for row in rows:
        try:
            evidence = json.loads(row["evidence_json"] or "{}")
        except ValueError:
            evidence = {"parse_error": "evidence_json was not readable JSON"}
        prior = existing.get(row["dedupe_key"])
        items.append({
            "dedupe_key": row["dedupe_key"],
            "section": row["section"],
            "anchor_class": row["anchor_class"],
            "headline": row["headline"],
            "body": row["body"],
            "source_ref": row["source_ref"],
            "score": row["score"],
            "evidence": evidence,
            "prior_decision": prior["decision"] if prior else None,
            "prior_note": prior["note"] if prior else None,
        })

    def _json(raw, fallback):
        try:
            return json.loads(raw) if raw else fallback
        except ValueError:
            return fallback

    return {
        "packet_id": packet["id"],
        "built_at": packet["built_at"],
        "window_from": packet["window_from"],
        "window_to": packet["window_to"],
        "status": packet["status"],
        "degraded_reason": packet["degraded_reason"],
        "thresholds": _json(packet["thresholds_json"], {}),
        "stats": _json(packet["stats_json"], {}),
        "items": items,
    }
