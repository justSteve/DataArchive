"""Tests for the memory review pipeline core logic. [da-04r]

Run:  cd /root/projects/DataArchive && PYTHONPATH=python python3 -m unittest discover -s python/tests -v

These cover the parts where a wrong answer is invisible: the extraction filter
(which decides what counts as Steve speaking), the heartbeat's fail-closed
behaviour, the strike rule, the anchor classification that drives the
inference-versus-stated split, and adjudication idempotency.

One test in here exists specifically because of this enterprise's history —
`test_unknown_status_fails_closed`. A regression test that passes against the
code it was meant to catch is one of the six silent-failure defects that produced
this pipeline's brief, so the fail-closed branches are asserted directly rather
than assumed.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ.setdefault("MR_STATE_DIR", tempfile.mkdtemp(prefix="mr-state-"))
os.environ.setdefault("MR_LOG_DIR", tempfile.mkdtemp(prefix="mr-logs-"))
os.environ.setdefault("MR_DESK_DIR", tempfile.mkdtemp(prefix="mr-desk-"))
os.environ.setdefault("MR_LEDGER_DIR", tempfile.mkdtemp(prefix="mr-ledger-"))

from memory_review import (analyze, cmclient, collect, config, extract,  # noqa: E402
                           heartbeat, ledger, render, server, similarity)
from memory_review.store import Store  # noqa: E402


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ExtractionFilterTests(unittest.TestCase):
    """role='user' is not 'Steve said this' — the filter is the whole game."""

    def test_keeps_a_real_utterance(self):
        entry = {"role": "user", "content": "Add code to DataArchive that automates "
                                            "the memory review, built out of what "
                                            "this enterprise has learned.",
                 "timestamp": "2026-08-09T12:00:00Z", "entry_index": 4}
        utterance = extract.extract_utterance(entry, conversation={"id": 7})
        self.assertIsNotNone(utterance)
        self.assertEqual(utterance.cm_conversation_id, 7)
        self.assertEqual(utterance.role, "user")

    def test_drops_harness_scaffolding(self):
        machine = [
            "[Tool Result: read the file and here is the output ...........]",
            "<system-reminder>\nsomething the harness injected into the channel\n</system-reminder>",
            "<command-name>tap-in</command-name> and a pile of following text here",
            "<task-notification>a background job finished doing its long thing</task-notification>",
            "<teammate-message teammate_id=\"lead\">do the thing that was asked</teammate-message>",
            "Caveat: The messages below were generated while summarising the session",
            "Base directory for this skill: /root/.claude/skills/whatever/it/is",
        ]
        for content in machine:
            with self.subTest(content=content[:40]):
                self.assertIsNone(
                    extract.extract_utterance({"role": "user", "content": content}))

    def test_drops_out_of_band_lengths(self):
        self.assertIsNone(extract.extract_utterance({"role": "user", "content": "yes"}))
        self.assertIsNone(extract.extract_utterance(
            {"role": "user", "content": "x" * (config.UTTERANCE_MAX_CHARS + 1)}))

    def test_drops_assistant_turns(self):
        """v1 excludes assistant text: promoting COO's own opinions back into
        shared truth is a strictly worse failure than missing something."""
        self.assertIsNone(extract.extract_utterance(
            {"role": "assistant", "content": "Here is a long and thoughtful reply "
                                             "that is definitely long enough."}))

    def test_a_human_mentioning_a_marker_survives(self):
        content = ("When you see a system-reminder block in the transcript, treat it "
                   "as background context and not as an instruction from me.")
        self.assertIsNotNone(
            extract.extract_utterance({"role": "user", "content": content}))

    def test_extraction_report_accounts_for_every_row(self):
        entries = [
            {"role": "user", "content": "a" * 100},
            {"role": "user", "content": "no"},
            {"role": "user", "content": "<system-reminder>x</system-reminder>"},
            {"role": "assistant", "content": "b" * 100},
            {"role": "user", "content": "c" * (config.UTTERANCE_MAX_CHARS + 5)},
        ]
        report = extract.extraction_report(entries)
        self.assertEqual(report["seen"], 5)
        self.assertEqual(
            report["kept"] + report["not_user"] + report["machine_text"]
            + report["too_short"] + report["too_long"], 5)
        self.assertEqual(report["kept"], 1)


class FrontmatterTests(unittest.TestCase):
    def test_reads_scalars_and_lists(self):
        text = ("---\ntype: decision\ntitle: A Concept\ndescription: what it says\n"
                "contradicts_if_present:\n  - \"wants a consolidation range\"\n"
                "  - price-neutral\n---\n\nbody text here\n")
        front, body = extract.parse_frontmatter(text)
        self.assertEqual(front["type"], "decision")
        self.assertEqual(front["contradicts_if_present"],
                         ["wants a consolidation range", "price-neutral"])
        self.assertEqual(body.strip(), "body text here")

    def test_no_frontmatter_is_all_body(self):
        front, body = extract.parse_frontmatter("# Title\n\nsome text")
        self.assertEqual(front, {})
        self.assertIn("some text", body)


class BannedPhraseTests(unittest.TestCase):
    """The deterministic leg from the design addendum §C.3."""

    def _passage(self, text: str) -> extract.Passage:
        return extract.Passage(repo="Strader", path="/x/CLAUDE.md", heading="Flies",
                               start_line=100, end_line=110, text=text,
                               text_hash="h")

    def test_flags_a_real_violation(self):
        passage = self._passage("Center the fly where the trade wants a "
                                "consolidation range to develop.")
        hits = extract.find_banned_phrases(["wants a consolidation range"], [passage])
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["line"], 100)

    def test_does_not_flag_the_prohibition_itself(self):
        """The 2026-08-05 butterfly fix put the ban INTO CLAUDE.md. A naive grep
        reports the prohibition as the violation."""
        passage = self._passage("Never write that a fly wants a consolidation range.")
        self.assertEqual(
            extract.find_banned_phrases(["wants a consolidation range"], [passage]), [])

    def test_does_not_flag_a_blockquote(self):
        passage = self._passage("> a fly wants a consolidation range")
        self.assertEqual(
            extract.find_banned_phrases(["wants a consolidation range"], [passage]), [])

    def test_no_declared_phrases_means_no_output(self):
        self.assertEqual(extract.find_banned_phrases([], [self._passage("anything")]), [])


class SimilarityTests(unittest.TestCase):
    def test_identical_text_scores_one(self):
        self.assertAlmostEqual(similarity.similarity("the same words", "the same words"),
                               1.0, places=6)

    def test_unrelated_text_scores_low(self):
        score = similarity.similarity(
            "butterfly strikes around the consolidation range",
            "the backup tarball hashing pass ran overnight on drive Z")
        self.assertLess(score, 0.2)

    def test_opposites_score_high_which_is_the_point(self):
        """Similarity measures aboutness. Contradiction sits at the top of the
        ranking next to violent agreement — which is why nothing here decides."""
        score = similarity.similarity(
            "center the fly on the consolidation range",
            "never center a fly on the consolidation range")
        self.assertGreater(score, 0.5)

    def test_index_query_respects_threshold_and_exclusion(self):
        index = similarity.LexicalIndex()
        index.add("a", "orderflow measurement of the SPX scalp proxy", {"t": 1})
        index.add("b", "drive hashing and the archive manifest", {"t": 2})
        self.assertEqual(index.query("orderflow measurement of the SPX scalp proxy",
                                     k=5, threshold=0.9, exclude=["a"]), [])
        hits = index.query("orderflow measurement of the SPX scalp proxy", k=5,
                           threshold=0.3)
        self.assertEqual(hits[0][0], "a")

    def test_empty_index_reports_degraded(self):
        self.assertEqual(similarity.LexicalIndex().health(), "degraded")

    def test_cluster_groups_restatements(self):
        pairs = [
            ("1", "never propose de-forking a zepo as hygiene, forks are deliberate"),
            ("2", "forks are deliberate appropriation — do not propose de-forking"),
            ("3", "the drive hashing pass should tee its output to data logs"),
        ]
        clusters = similarity.cluster(pairs, 0.3)
        biggest = clusters[0]
        self.assertIn("1", biggest)
        self.assertIn("2", biggest)
        self.assertNotIn("3", biggest)

    def test_centroid_is_a_real_member(self):
        texts = ["alpha beta gamma", "alpha beta gamma delta", "totally other words"]
        self.assertIn(similarity.centroid_text(texts), texts)


class HeartbeatTests(unittest.TestCase):
    def test_empty_run_is_ok_and_carries_its_inputs(self):
        report = heartbeat.RunReport(job="t")
        report.assert_nonempty("inputs", [1, 2, 3])
        report.count("candidates_emitted", 0)
        report.count("entries_scanned", 1840)
        self.assertEqual(report.status, heartbeat.OK)
        self.assertEqual(report.exit_code(), 0)
        doc = report.as_dict()
        self.assertEqual(doc["counters"]["candidates_emitted"], 0)
        self.assertEqual(doc["counters"]["entries_scanned"], 1840)

    def test_missing_input_fails_it_does_not_skip(self):
        report = heartbeat.RunReport(job="t")
        report.assert_nonempty("inputs", [])
        self.assertEqual(report.status, heartbeat.FAILED)
        self.assertEqual(report.exit_code(), 2)

    def test_stale_input_degrades(self):
        report = heartbeat.RunReport(job="t")
        old = datetime.now(timezone.utc) - timedelta(days=20)
        report.assert_fresh("corpus", old, 3600, severity=heartbeat.DEGRADED)
        self.assertEqual(report.status, heartbeat.DEGRADED)
        self.assertEqual(report.exit_code(), 1)

    def test_unparseable_freshness_is_not_a_pass(self):
        report = heartbeat.RunReport(job="t")
        report.assert_fresh("corpus", None, 3600, severity=heartbeat.DEGRADED)
        self.assertEqual(report.status, heartbeat.DEGRADED)

    def test_unknown_status_fails_closed(self):
        self.assertEqual(heartbeat.worst("ok", "banana"), heartbeat.FAILED)
        self.assertEqual(heartbeat.worst("ok", "ok"), heartbeat.OK)
        self.assertEqual(heartbeat.worst("ok", "degraded"), heartbeat.DEGRADED)

    def test_evaluate_distinguishes_never_ran_from_found_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hb.json"
            self.assertEqual(heartbeat.evaluate(path, 3600)["state"], "missing")

            report = heartbeat.RunReport(job="t")
            report.count("candidates", 0)
            heartbeat.write(path, report.as_dict())
            verdict = heartbeat.evaluate(path, 3600)
            self.assertEqual(verdict["state"], "ok")
            self.assertEqual(verdict["document"]["counters"]["candidates"], 0)

            doc = report.as_dict()
            doc["ts"] = _iso(datetime.now(timezone.utc) - timedelta(days=3))
            heartbeat.write(path, doc)
            self.assertEqual(heartbeat.evaluate(path, 3600)["state"], "stale")

    def test_evaluate_fails_closed_on_unknown_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hb.json"
            heartbeat.write(path, {"ts": _iso(datetime.now(timezone.utc)),
                                   "status": "greenish"})
            self.assertEqual(heartbeat.evaluate(path, 3600)["state"], "failed")

    def test_write_is_atomic_and_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "hb.json"
            heartbeat.write(path, {"ts": _iso(datetime.now(timezone.utc)),
                                   "status": "ok"})
            self.assertEqual(json.loads(path.read_text())["status"], "ok")
            self.assertEqual([p for p in path.parent.iterdir()
                              if p.name.startswith(".hb-")], [])
            self.assertEqual(oct(path.stat().st_mode)[-3:], "644",
                             "other tooling reads these; 0600 from mkstemp leaks")


class CMTimestampTests(unittest.TestCase):
    def test_parses_both_shapes_cm_emits(self):
        for raw in ("2026-08-09T15:58:01.000Z", "2026-08-09 15:58:01"):
            with self.subTest(raw=raw):
                parsed = cmclient.parse_cm_timestamp(raw)
                self.assertIsNotNone(parsed)
                self.assertEqual(parsed.year, 2026)

    def test_unparseable_returns_none_rather_than_now(self):
        self.assertIsNone(cmclient.parse_cm_timestamp("not a timestamp"))
        self.assertIsNone(cmclient.parse_cm_timestamp(""))


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "review.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _item(self, key="auto-memory:/x/a.md", body="body one"):
        return {"kind": "auto-memory", "item_key": key, "repo": "COO",
                "source_path": "/x/a.md", "title": "A", "description": "d",
                "frontmatter": {}, "body": body,
                "body_hash": extract.content_hash(body), "mtime": "2026-08-09T00:00:00Z"}

    def test_upsert_reports_new_changed_unchanged(self):
        run = self.store.start_run("collect", None)
        self.assertEqual(self.store.upsert_memory_item(run, self._item()), "new")
        self.assertEqual(self.store.upsert_memory_item(run, self._item()), "unchanged")
        self.assertEqual(
            self.store.upsert_memory_item(run, self._item(body="body two")), "changed")

    def test_utterance_insert_is_deduped_by_hash(self):
        run = self.store.start_run("collect", None)
        row = {"role": "user", "content": "x" * 60,
               "content_hash": extract.content_hash("x" * 60),
               "ts": "2026-08-09T10:00:00Z", "cm_conversation_id": 1,
               "cm_conversation_uuid": "u", "project": "COO", "entry_index": 1}
        self.assertEqual(self.store.insert_utterances(run, [row]), 1)
        self.assertEqual(self.store.insert_utterances(run, [row]), 0)
        self.assertEqual(self.store.utterance_count(), 1)

    def test_finish_run_rejects_unknown_fields(self):
        run = self.store.start_run("collect", None)
        with self.assertRaises(ValueError):
            self.store.finish_run(run, statuss="ok")

    def test_adjudication_is_idempotent_and_updatable(self):
        packet = self.store.create_packet(
            window_from=None, window_to=None, status="ok", degraded_reason=None,
            thresholds={}, stats={}, run_id=None)
        self.store.add_packet_items(packet, [{
            "section": "new_memory", "dedupe_key": "k1", "anchor_class": "coo_inference",
            "headline": "H", "body": "B", "source_ref": "/x", "evidence": {},
            "score": None}])
        self.assertEqual(self.store.record_adjudication(
            packet_id=packet, dedupe_key="k1", section="new_memory",
            decision="confirm", note=None, decided_at="2026-08-09T00:00:00Z",
            client_id="c"), "inserted")
        self.assertEqual(self.store.record_adjudication(
            packet_id=packet, dedupe_key="k1", section="new_memory",
            decision="discard", note="wrong", decided_at="2026-08-09T00:05:00Z",
            client_id="c"), "updated")
        rows = self.store.adjudications_for_packet(packet)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["decision"], "discard")

    def test_tombstone_requires_a_reason(self):
        with self.assertRaises(ValueError):
            self.store.add_tombstone("k", "text", "   ")


class StrikeRuleTests(unittest.TestCase):
    """≥3 occurrences, ≥3 sessions, ≥3 days — all three, or it does not strike."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "review.db")
        self.run = self.store.start_run("collect", None)
        self.concepts = similarity.LexicalIndex()
        self.concepts.add("unrelated", "drive hashing manifests and archive coverage",
                          {"title": "Drives"})

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _add(self, text, conv, day):
        self.store.insert_utterances(self.run, [{
            "role": "user", "content": text,
            "content_hash": extract.content_hash(text + str(conv) + day),
            "ts": f"{day}T10:00:00Z", "cm_conversation_id": conv,
            "cm_conversation_uuid": f"u{conv}", "project": "COO", "entry_index": 1}])

    def test_three_sessions_three_days_strikes(self):
        text = ("never propose de-forking a zepo as hygiene because forks are a "
                "deliberate appropriation of superior intelligence")
        for i, day in enumerate(["2026-08-01", "2026-08-03", "2026-08-05"]):
            self._add(text + f" restated {i}", conv=i + 1, day=day)
        items, stats = analyze.section_graduation(
            self.store, self.store.utterances_since(), self.concepts, 5)
        self.assertEqual(stats["struck"], 1)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["anchor_class"], analyze.ANCHOR_STATED)

    def test_same_day_does_not_strike(self):
        text = "the same insistent point restated three times in one sitting"
        for i in range(3):
            self._add(text + f" again {i}", conv=i + 1, day="2026-08-01")
        _, stats = analyze.section_graduation(
            self.store, self.store.utterances_since(), self.concepts, 5)
        self.assertEqual(stats["struck"], 0)

    def test_one_session_does_not_strike(self):
        text = "the same insistent point restated across several days but one session"
        for day in ["2026-08-01", "2026-08-03", "2026-08-05"]:
            self._add(text + f" on {day}", conv=1, day=day)
        _, stats = analyze.section_graduation(
            self.store, self.store.utterances_since(), self.concepts, 5)
        self.assertEqual(stats["struck"], 0)

    def test_already_curated_is_subtracted(self):
        text = ("drive hashing manifests and archive coverage need a ledger that "
                "reports what it does not cover")
        for i, day in enumerate(["2026-08-01", "2026-08-03", "2026-08-05"]):
            self._add(text + f" point {i}", conv=i + 1, day=day)
        items, stats = analyze.section_graduation(
            self.store, self.store.utterances_since(), self.concepts, 5)
        self.assertEqual(stats["already_covered"], 1)
        self.assertEqual(items, [])

    def test_tombstone_suppresses_and_is_counted(self):
        text = ("never propose de-forking a zepo as hygiene because forks are a "
                "deliberate appropriation of superior intelligence")
        for i, day in enumerate(["2026-08-01", "2026-08-03", "2026-08-05"]):
            self._add(text + f" restated {i}", conv=i + 1, day=day)
        self.store.add_tombstone("prior", text, "already settled, stop asking")
        items, stats = analyze.section_graduation(
            self.store, self.store.utterances_since(), self.concepts, 5)
        self.assertEqual(stats["suppressed_by_tombstone"], 1)
        self.assertEqual(items, [])
        self.assertEqual(self.store.active_tombstones()[0]["suppressed_count"], 1)


class AnchorClassificationTests(unittest.TestCase):
    """The split that is the point of the whole exercise.

    Anchoring is distinctive-vocabulary overlap with absolute floors, not
    trigram similarity. The trigram version was measured on the live corpus on
    2026-08-09 and labelled 40 of 40 memory cards "Steve stated this", including
    a v_down trading card anchored to "good distinctions made there. great job."
    A classifier that always says yes is not a classifier.
    """

    STATEMENT = ("I live and die by full SPX. Never propose XSP or SPY step-downs "
                 "again — size the position via structure instead: strike "
                 "selection, days to expiry, and spread width are the levers, not "
                 "a smaller underlying.")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "review.db")
        run = self.store.start_run("collect", None)
        self.store.insert_utterances(run, [{
            "role": "user", "content": self.STATEMENT,
            "content_hash": extract.content_hash(self.STATEMENT),
            "ts": "2026-07-22T10:00:00Z", "cm_conversation_id": 1,
            "cm_conversation_uuid": "u1", "project": "Strader", "entry_index": 1}])
        self.corpus = analyze.build_utterance_index(self.store.utterances_since())

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_supported_claim_is_stated_and_carries_the_quote(self):
        claim = ("SPX only: never propose XSP or SPY step-downs. Size the position "
                 "via structure instead — strike selection, days to expiry and "
                 "spread width are the levers, not a smaller underlying.")
        anchor, evidence = analyze.classify_anchor(claim, self.corpus)
        self.assertEqual(anchor, analyze.ANCHOR_STATED)
        self.assertTrue(evidence)
        self.assertIn("SPX", evidence[0]["quote"])
        self.assertEqual(evidence[0]["day"], "2026-07-22")
        self.assertGreaterEqual(evidence[0]["shared_words"],
                                config.ANCHOR_MIN_SHARED_TOKENS)

    def test_unsupported_claim_is_flagged_as_an_inference(self):
        anchor, evidence = analyze.classify_anchor(
            "Steve prefers iron condors on quiet Tuesdays in the afternoon session",
            self.corpus)
        self.assertEqual(anchor, analyze.ANCHOR_INFERENCE)
        self.assertEqual(evidence, [])

    def test_a_topical_but_thin_overlap_does_not_anchor(self):
        """The failure the floors exist to prevent: same subject, few shared
        distinctive words, which a ratio-only scorer reads as a match."""
        anchor, _ = analyze.classify_anchor("SPX structure sizing", self.corpus)
        self.assertEqual(anchor, analyze.ANCHOR_INFERENCE)

    def test_an_empty_corpus_makes_everything_an_inference(self):
        empty = analyze.build_utterance_index([])
        anchor, _ = analyze.classify_anchor(self.STATEMENT, empty)
        self.assertEqual(anchor, analyze.ANCHOR_INFERENCE)


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "adjudications.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def test_unknown_decision_is_rejected(self):
        with self.assertRaises(ValueError):
            ledger.record(packet_id=1, dedupe_key="k", section="s",
                          decision="maybe-ish", note=None, decided_at=None)

    def test_append_only_newest_wins_on_replay(self):
        ledger.append([ledger.record(packet_id=1, dedupe_key="k", section="s",
                                     decision="confirm", note=None,
                                     decided_at="2026-08-09T10:00:00Z")], self.path)
        ledger.append([ledger.record(packet_id=1, dedupe_key="k", section="s",
                                     decision="discard", note="wrong",
                                     decided_at="2026-08-09T11:00:00Z")], self.path)
        self.assertEqual(len(self.path.read_text().strip().splitlines()), 2)
        state = ledger.replay(self.path)
        self.assertEqual(state[(1, "k")]["decision"], "discard")

    def test_malformed_lines_are_skipped_not_fatal(self):
        self.path.write_text('{"packet_id":1,"dedupe_key":"a","decision":"confirm"}\n'
                             "this line is not json\n")
        self.assertEqual(len(list(ledger.iter_entries(self.path))), 1)


class SubmissionTests(unittest.TestCase):
    """The capture path. A 200 here must mean the write actually landed."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "review.db"
        self.ledger_path = Path(self.tmp.name) / "adjudications.jsonl"
        self._real_ledger = config.ADJUDICATION_LEDGER
        config.ADJUDICATION_LEDGER = self.ledger_path
        ledger.config.ADJUDICATION_LEDGER = self.ledger_path

        with Store(self.db) as store:
            self.packet = store.create_packet(
                window_from=None, window_to=None, status="ok", degraded_reason=None,
                thresholds={}, stats={}, run_id=None)
            store.add_packet_items(self.packet, [
                {"section": "new_memory", "dedupe_key": "k1",
                 "anchor_class": "coo_inference", "headline": "An inference",
                 "body": "body", "source_ref": "/x", "evidence": {}, "score": None},
                {"section": "contradiction", "dedupe_key": "k2",
                 "anchor_class": "not_applicable", "headline": "A collision",
                 "body": "body", "source_ref": "/y", "evidence": {}, "score": 0.4},
            ])

    def tearDown(self):
        config.ADJUDICATION_LEDGER = self._real_ledger
        ledger.config.ADJUDICATION_LEDGER = self._real_ledger
        self.tmp.cleanup()

    def _submit(self, decisions, **extra):
        return server.apply_submission(
            {"packet_id": self.packet, "client_id": "test", "decisions": decisions,
             **extra}, db_path=self.db)

    def test_records_to_store_and_ledger(self):
        result = self._submit([{"dedupe_key": "k1", "decision": "confirm",
                                "note": "", "decided_at": "2026-08-09T10:00:00Z"}])
        self.assertTrue(result["ok"])
        self.assertEqual(result["inserted"], 1)
        self.assertEqual(len(self.ledger_path.read_text().strip().splitlines()), 1)

    def test_resubmission_updates_rather_than_duplicating(self):
        self._submit([{"dedupe_key": "k1", "decision": "confirm", "note": ""}])
        result = self._submit([{"dedupe_key": "k1", "decision": "defer", "note": ""}])
        self.assertEqual(result["updated"], 1)
        with Store(self.db) as store:
            self.assertEqual(len(store.adjudications_for_packet(self.packet)), 1)

    def test_unknown_decision_is_rejected_whole(self):
        result = self._submit([
            {"dedupe_key": "k1", "decision": "confirm", "note": ""},
            {"dedupe_key": "k2", "decision": "sure-why-not", "note": ""}])
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], 400)
        with Store(self.db) as store:
            self.assertEqual(store.adjudications_for_packet(self.packet), [])
        self.assertFalse(self.ledger_path.exists())

    def test_unknown_item_is_rejected(self):
        result = self._submit([{"dedupe_key": "not-in-packet", "decision": "confirm"}])
        self.assertFalse(result["ok"])
        self.assertIn("not an item of packet", result["error"])

    def test_unknown_packet_is_rejected(self):
        result = server.apply_submission(
            {"packet_id": 99999, "decisions": [{"dedupe_key": "k1",
                                                "decision": "confirm"}]},
            db_path=self.db)
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], 404)

    def test_discard_without_a_reason_is_refused(self):
        result = self._submit([{"dedupe_key": "k1", "decision": "discard", "note": ""}])
        self.assertFalse(result["ok"])
        self.assertIn("no reason", result["error"])

    def test_discard_with_a_reason_writes_a_tombstone(self):
        result = self._submit([{"dedupe_key": "k1", "decision": "discard",
                                "note": "this was never my position"}])
        self.assertTrue(result["ok"])
        with Store(self.db) as store:
            tombstones = store.active_tombstones()
        self.assertEqual(len(tombstones), 1)
        self.assertEqual(tombstones[0]["reason"], "this was never my position")

    def test_partial_submission_does_not_advance_the_review_window(self):
        """Answering some items must not discard the rest. Advancing the window
        on any submission made 66 of 71 unanswered items vanish from the next
        packet — observed during the build, 2026-08-09."""
        result = self._submit([{"dedupe_key": "k1", "decision": "confirm"}])
        self.assertTrue(result["ok"])
        self.assertEqual(result["outstanding"], 1)
        self.assertFalse(result["packet_complete"])
        with Store(self.db) as store:
            self.assertIsNone(store.get_cursor(analyze.LAST_REVIEW_CURSOR))

    def test_completing_a_packet_advances_the_review_window(self):
        self._submit([{"dedupe_key": "k1", "decision": "confirm"},
                      {"dedupe_key": "k2", "decision": "defer"}])
        with Store(self.db) as store:
            self.assertIsNotNone(store.get_cursor(analyze.LAST_REVIEW_CURSOR))

    def test_empty_batch_is_rejected(self):
        self.assertFalse(self._submit([])["ok"])

    def test_graduate_records_a_proposal_and_writes_no_bundle(self):
        result = self._submit([{"dedupe_key": "k2", "decision": "graduate",
                                "note": "worth curating"}])
        self.assertTrue(result["ok"])
        self.assertEqual(result["graduation_proposals"], 1)
        self.assertIn("Nothing here wrote to a knowledge bundle", result["note"])


class GovernanceTests(unittest.TestCase):
    """The pipeline PROPOSES. It must not be able to write shared truth.

    Asserted functionally rather than by grepping for suspicious strings: hash
    every file of a synthetic knowledge bundle and always-loaded surface, run a
    full collect-free build and publish over it, and require every hash to be
    unchanged. A source-text check would pass the moment someone renamed a
    variable; this one only passes if nothing was written.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        repo = root / "projects" / "TestRepo"
        (repo / ".claude" / "rules").mkdir(parents=True)
        (repo / "CLAUDE.md").write_text(
            "# TestRepo\n\n## Rules\n\nAlways body the fly at the destination "
            "price rather than centring it on any range at all.\n", encoding="utf-8")
        (repo / ".claude" / "rules" / "a-rule.md").write_text(
            "# Rule\n\nThe consolidation range is a landmark and never a centring "
            "requirement for a butterfly structure.\n", encoding="utf-8")
        bundle = repo / "conventions"
        bundle.mkdir()
        (bundle / "log.md").write_text("# Log\n\nappend-only\n", encoding="utf-8")
        (bundle / "a-concept.md").write_text(
            "---\ntype: decision\ntitle: A Concept\ndescription: d\n---\n\n"
            "Body the fly at the destination price.\n", encoding="utf-8")
        memories = root / "claude-projects" / "-root-projects-TestRepo" / "memory"
        memories.mkdir(parents=True)
        (memories / "card.md").write_text(
            "---\nname: card\ndescription: d\n---\n\nSomething COO inferred.\n",
            encoding="utf-8")

        self.protected = sorted(
            list(bundle.rglob("*.md")) + list(repo.glob("CLAUDE.md"))
            + list((repo / ".claude" / "rules").glob("*.md"))
            + list(memories.glob("*.md")))
        self.before = {p: extract.content_hash(p.read_text(encoding="utf-8"))
                       for p in self.protected}
        self.before_mtimes = {p: p.stat().st_mtime_ns for p in self.protected}

        self.layout = config.Layout(
            surfaces=[config.Surface(repo="TestRepo", root=repo,
                                     claude_md=repo / "CLAUDE.md",
                                     rules_dir=repo / ".claude" / "rules")],
            bundles=[config.Bundle(repo="TestRepo", path=bundle)],
            memory_dirs=[memories])
        self.db = root / "review.db"

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_full_build_and_publish_writes_nothing_into_a_bundle(self):
        with Store(self.db) as store:
            run = store.start_run("collect", None)
            for item in extract.collect_memory_items(self.layout):
                store.upsert_memory_item(run, item.as_row())
            store.replace_instruction_passages(
                run, [p.as_row() for p in extract.segment_instructions(self.layout)])
            store.finish_run(run, status="ok")

            packet_id, _ = analyze.build(
                store=store, layout=self.layout,
                window_from="2000-01-01T00:00:00Z", write_heartbeat=False)
            self.assertIsNotNone(packet_id)
            payload = analyze.packet_payload(store, packet_id)
            render.write_page(payload,
                              path=Path(self.tmp.name) / "desk-memory-review.html")

            server.apply_submission(
                {"packet_id": packet_id, "client_id": "gov",
                 "decisions": [{"dedupe_key": payload["items"][0]["dedupe_key"],
                                "decision": "graduate",
                                "note": "promote this"}]},
                db_path=self.db)

        for path in self.protected:
            with self.subTest(path=path.name):
                self.assertEqual(
                    extract.content_hash(path.read_text(encoding="utf-8")),
                    self.before[path],
                    f"{path} was modified by the pipeline")
                self.assertEqual(path.stat().st_mtime_ns, self.before_mtimes[path],
                                 f"{path} was rewritten by the pipeline")

    def test_no_new_files_appear_in_a_bundle(self):
        bundle = self.layout.bundles[0].path
        before = {p.name for p in bundle.rglob("*")}
        with Store(self.db) as store:
            run = store.start_run("collect", None)
            for item in extract.collect_memory_items(self.layout):
                store.upsert_memory_item(run, item.as_row())
            store.replace_instruction_passages(
                run, [p.as_row() for p in extract.segment_instructions(self.layout)])
            store.finish_run(run, status="ok")
            analyze.build(store=store, layout=self.layout,
                          window_from="2000-01-01T00:00:00Z", write_heartbeat=False)
        self.assertEqual({p.name for p in bundle.rglob("*")}, before)


class RenderTests(unittest.TestCase):
    def _payload(self, **overrides):
        payload = {
            "packet_id": 1, "built_at": "2026-08-09T12:00:00Z",
            "window_from": "2026-08-02T00:00:00Z", "window_to": "2026-08-09T00:00:00Z",
            "status": "ok", "degraded_reason": None,
            "thresholds": {}, "stats": {"corpus": {"utterances_in_window": 12},
                                        "sections": {"anchor:coo_inference": 1},
                                        "backend": "lexical-trigram-jaccard/1"},
            "items": [{
                "dedupe_key": "k1", "section": "new_memory",
                "anchor_class": "coo_inference", "headline": "An inferred claim",
                "body": "body", "source_ref": "/x/a.md",
                "score": None, "evidence": {"anchors": []},
                "prior_decision": None, "prior_note": None}],
        }
        payload.update(overrides)
        return payload

    def test_page_embeds_the_packet_and_a_form(self):
        markup = render.render(self._payload())
        self.assertIn('id="packet"', markup)
        self.assertIn('type="radio"', markup)
        self.assertIn("/api/adjudications", markup)
        self.assertIn("localStorage", markup)
        self.assertIn("An inferred claim", markup)

    def test_degraded_packet_carries_a_visible_banner(self):
        markup = render.render(self._payload(status="degraded",
                                             degraded_reason="corpus stale"))
        self.assertIn("THIS PACKET IS DEGRADED", markup)
        self.assertIn("corpus stale", markup)

    def test_injected_markup_cannot_break_out_of_the_embedded_json(self):
        """A packet carrying `</script>` must not close the JSON block early.

        Item text is rendered client-side through the page's own escaper, so the
        server-side defence is the JSON block: every `<` is emitted as \\u003c,
        which a JSON parser reads identically and an HTML parser does not read as
        a tag at all.
        """
        payload = self._payload()
        payload["items"][0]["headline"] = "<script>alert(1)</script>"
        markup = render.render(payload)
        self.assertNotIn("<script>alert(1)", markup)
        self.assertNotIn("</script>alert", markup)
        self.assertIn("\\u003cscript>alert(1)", markup)
        # exactly two real <script> elements: the packet block and the page code
        self.assertEqual(markup.count("</script>"), 2)

    def test_html_chrome_is_escaped(self):
        payload = self._payload(degraded_reason='corpus <b>stale</b> & "unread"',
                                status="degraded")
        markup = render.render(payload)
        self.assertIn("&lt;b&gt;stale&lt;/b&gt;", markup)

    def test_write_page_is_atomic(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "desk-memory-review.html"
            render.write_page(self._payload(), path=path)
            self.assertTrue(path.is_file())
            self.assertEqual([p for p in path.parent.iterdir()
                              if p.name.startswith(".desk-")], [])
            self.assertEqual(oct(path.stat().st_mode)[-3:], "644",
                             "Steve reads the page from Windows over the 9p share")


class PacketBuildTests(unittest.TestCase):
    """End-to-end over a synthetic layout, with no CM and no network."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.db = root / "review.db"

        projects = root / "projects"
        repo = projects / "TestRepo"
        (repo / ".claude" / "rules").mkdir(parents=True)
        (repo / "CLAUDE.md").write_text(
            "# TestRepo\n\n## Flies\n\nCenter the fly on the consolidation range so "
            "the trade sits where price is expected to settle at the close of the "
            "session, which is the framing we use everywhere.\n", encoding="utf-8")
        bundle = repo / "conventions"
        bundle.mkdir()
        (bundle / "fly-placement.md").write_text(
            "---\ntype: decision\ntitle: Fly Placement\n"
            "description: bodies go at the destination\n"
            "contradicts_if_present:\n  - \"center the fly on the consolidation range\"\n"
            "---\n\nBody the fly at the destination price. The consolidation range is "
            "a landmark, never a centring requirement for the structure.\n",
            encoding="utf-8")

        memories = root / "claude-projects" / "-root-projects-TestRepo" / "memory"
        memories.mkdir(parents=True)
        (memories / "feedback_fly-placement.md").write_text(
            "---\nname: fly-placement\ndescription: bodies at destination\n---\n\n"
            "Body the fly at the destination price, not centred on a range.\n",
            encoding="utf-8")

        self.layout = config.Layout(
            surfaces=[config.Surface(repo="TestRepo", root=repo,
                                     claude_md=repo / "CLAUDE.md",
                                     rules_dir=repo / ".claude" / "rules")],
            bundles=[config.Bundle(repo="TestRepo", path=bundle)],
            memory_dirs=[memories])

        self.store = Store(self.db)
        run = self.store.start_run("collect", None)
        for item in extract.collect_memory_items(self.layout):
            self.store.upsert_memory_item(run, item.as_row())
        self.store.replace_instruction_passages(
            run, [p.as_row() for p in extract.segment_instructions(self.layout)])
        self.store.finish_run(run, status="ok")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_build_produces_a_packet_with_the_contradiction(self):
        packet_id, report = analyze.build(
            store=self.store, layout=self.layout,
            window_from="2000-01-01T00:00:00Z", write_heartbeat=False)
        self.assertIsNotNone(packet_id)
        self.assertEqual(report.status, heartbeat.OK, report.summary_line())

        payload = analyze.packet_payload(self.store, packet_id)
        sections = {item["section"] for item in payload["items"]}
        self.assertIn(analyze.SECTION_CONTRADICTION, sections)

        banned = [i for i in payload["items"]
                  if i["evidence"].get("leg") == "deterministic"]
        self.assertTrue(banned, "the declared banned phrase was not detected")
        self.assertIn("CLAUDE.md", banned[0]["source_ref"])

    def test_auto_memory_with_no_utterance_is_an_inference(self):
        packet_id, _ = analyze.build(
            store=self.store, layout=self.layout,
            window_from="2000-01-01T00:00:00Z", write_heartbeat=False)
        payload = analyze.packet_payload(self.store, packet_id)
        new_items = [i for i in payload["items"]
                     if i["section"] == analyze.SECTION_NEW]
        self.assertTrue(new_items)
        self.assertTrue(all(i["anchor_class"] == analyze.ANCHOR_INFERENCE
                            for i in new_items),
                        "with an empty utterance corpus everything must read as "
                        "an inference — that is the honest answer")

    def test_build_without_a_collection_run_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            with Store(Path(tmp) / "empty.db") as empty:
                packet_id, report = analyze.build(
                    store=empty, layout=self.layout, write_heartbeat=False)
            self.assertEqual(report.status, heartbeat.FAILED)
            self.assertIsNone(packet_id)

    def test_degraded_collection_degrades_the_packet(self):
        run = self.store.start_run("collect", None)
        self.store.finish_run(run, status="degraded")
        _, report = analyze.build(store=self.store, layout=self.layout,
                                  window_from="2000-01-01T00:00:00Z",
                                  write_heartbeat=False)
        self.assertEqual(report.status, heartbeat.DEGRADED)

    def test_unrecognised_collection_status_fails_closed(self):
        run = self.store.start_run("collect", None)
        self.store.finish_run(run, status="greenish")
        _, report = analyze.build(store=self.store, layout=self.layout,
                                  window_from="2000-01-01T00:00:00Z",
                                  write_heartbeat=False)
        self.assertEqual(report.status, heartbeat.FAILED)

    def test_answered_items_are_not_asked_again(self):
        packet_id, _ = analyze.build(store=self.store, layout=self.layout,
                                     window_from="2000-01-01T00:00:00Z",
                                     write_heartbeat=False)
        payload = analyze.packet_payload(self.store, packet_id)
        first_key = payload["items"][0]["dedupe_key"]
        self.store.record_adjudication(
            packet_id=packet_id, dedupe_key=first_key, section="new_memory",
            decision="confirm", note=None, decided_at="2026-08-09T00:00:00Z",
            client_id="t")

        second_id, _ = analyze.build(store=self.store, layout=self.layout,
                                     window_from="2000-01-01T00:00:00Z",
                                     write_heartbeat=False)
        second = analyze.packet_payload(self.store, second_id)
        self.assertNotIn(first_key, {i["dedupe_key"] for i in second["items"]})


class PaginationTests(unittest.TestCase):
    """CM caps `limit` below what we ask for. Stopping on a SHORT page truncated
    a 50-day window to its first 100 conversations and reported ok."""

    class Resp:
        def __init__(self, payload):
            self.payload = json.dumps(payload).encode("utf-8")
            self.status = 200

        def read(self):
            return self.payload

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def test_walks_past_a_server_capped_short_page(self):
        pages = {1: [{"id": i} for i in range(100)],
                 2: [{"id": i} for i in range(100, 150)],
                 3: []}
        seen = []

        def opener(url, timeout=None):
            page = int(url.split("page=")[1].split("&")[0])
            seen.append(page)
            return self.Resp({"data": pages.get(page, [])})

        with tempfile.TemporaryDirectory() as tmp:
            client = cmclient.CMClient(
                traffic_log=cmclient.TrafficLog(Path(tmp)), opener=opener)
            rows = client.conversations_since("2026-06-20T00:00:00Z", limit=200)
        self.assertEqual(len(rows), 150)
        self.assertEqual(seen, [1, 2, 3])

    def test_entries_walk_past_a_capped_short_page(self):
        pages = {1: [{"role": "user", "content": "x"}] * 100,
                 2: [{"role": "user", "content": "y"}] * 3,
                 3: []}

        def opener(url, timeout=None):
            page = int(url.split("page=")[1].split("&")[0])
            return self.Resp({"data": pages.get(page, [])})

        with tempfile.TemporaryDirectory() as tmp:
            client = cmclient.CMClient(
                traffic_log=cmclient.TrafficLog(Path(tmp)), opener=opener)
            self.assertEqual(len(list(client.conversation_entries(1))), 103)


class CollectionTests(unittest.TestCase):
    """Collection against a fake CM, so the failure paths are exercised."""

    class FakeResponse:
        def __init__(self, payload):
            self.payload = json.dumps(payload).encode("utf-8")
            self.status = 200

        def read(self):
            return self.payload

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "review.db"
        self.hb = Path(self.tmp.name) / "hb.json"
        self.layout = config.discover_layout()

    def tearDown(self):
        self.tmp.cleanup()

    def _client(self, opener):
        return cmclient.CMClient(
            traffic_log=cmclient.TrafficLog(Path(self.tmp.name)), opener=opener)

    def test_stale_corpus_degrades_and_holds_the_cursor(self):
        old = (datetime.now(timezone.utc) - timedelta(days=20)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")

        def opener(url, timeout=None):
            if "/health" in url:
                return self.FakeResponse({"status": "ok", "lastEntryTimestamp": old,
                                          "scheduler": {"lastRunStatus": "success"}})
            return self.FakeResponse({"data": []})

        with Store(self.db) as store:
            store.set_cursor("cm_conversations_since", "2026-08-01T00:00:00Z")
            report = collect.run(store=store, client=self._client(opener),
                                 layout=self.layout, heartbeat_path=self.hb)
            self.assertEqual(report.status, heartbeat.DEGRADED)
            self.assertEqual(store.get_cursor("cm_conversations_since"),
                             "2026-08-01T00:00:00Z")
        self.assertEqual(heartbeat.evaluate(self.hb, 3600)["state"], "degraded")

    def test_unreachable_cm_fails_and_still_writes_a_heartbeat(self):
        def opener(url, timeout=None):
            raise OSError("connection refused")

        with Store(self.db) as store:
            report = collect.run(store=store, client=self._client(opener),
                                 layout=self.layout, heartbeat_path=self.hb)
        self.assertEqual(report.status, heartbeat.FAILED)
        self.assertEqual(report.exit_code(), 2)
        verdict = heartbeat.evaluate(self.hb, 3600)
        self.assertEqual(verdict["state"], "failed")
        self.assertIn("cm_reachable", verdict["document"]["failed_assertions"])

    def test_healthy_empty_window_is_ok_and_advances_the_cursor(self):
        fresh = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        def opener(url, timeout=None):
            if "/health" in url:
                return self.FakeResponse({"status": "ok", "lastEntryTimestamp": fresh,
                                          "scheduler": {"lastRunStatus": "success"}})
            return self.FakeResponse({"data": []})

        with Store(self.db) as store:
            report = collect.run(store=store, client=self._client(opener),
                                 layout=self.layout, heartbeat_path=self.hb)
            self.assertEqual(report.status, heartbeat.OK, report.summary_line())
            self.assertIsNotNone(store.get_cursor("cm_conversations_since"))

        document = heartbeat.evaluate(self.hb, 3600)["document"]
        self.assertEqual(document["counters"]["conversations_seen"], 0)
        self.assertGreater(document["counters"]["memory_files_seen"], 0,
                           "an empty CM window must still show the local tiers were "
                           "read — that is what makes 'found nothing' credible")

    def test_traffic_is_logged_for_every_request_including_failures(self):
        def opener(url, timeout=None):
            raise OSError("connection refused")

        client = self._client(opener)
        with Store(self.db) as store:
            collect.run(store=store, client=client, layout=self.layout,
                        heartbeat_path=self.hb)
            summary = store.traffic_summary()
        self.assertGreaterEqual(summary["requests"], 1)
        self.assertGreaterEqual(summary["failed"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
