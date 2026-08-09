"""Daily collection: Claude Monitor and the local memory tiers into DataArchive. [da-04r]

One pass, four inputs, one heartbeat:

  * CM conversation entries since the cursor  → the utterance corpus (Steve's words)
  * auto-memory cards across every repo       → COO's distillations
  * OKF bundle concepts                       → curated shared truth
  * CLAUDE.md + .claude/rules/*.md everywhere → the always-loaded surface

The cursor advances **only** on a clean run. A degraded run leaves it where it
was so the skipped window is re-examined once the dependency recovers, instead of
being silently lost — the failure mode that cost this enterprise twenty days of
MemPalace ingest.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config, extract, heartbeat
from .cmclient import CMClient, CMError, CMUnavailable, TrafficLog
from .store import Store, utcnow

CURSOR_NAME = "cm_conversations_since"


def _default_since() -> str:
    start = datetime.now(timezone.utc) - timedelta(days=config.BOOTSTRAP_LOOKBACK_DAYS)
    return start.strftime("%Y-%m-%dT%H:%M:%SZ")


def run(store: Store | None = None,
        client: CMClient | None = None,
        layout: config.Layout | None = None,
        *,
        since: str | None = None,
        write_heartbeat: bool = True,
        heartbeat_path: Path | None = None) -> heartbeat.RunReport:
    """Execute one collection pass. Always returns a report; never returns silently.

    The caller decides what to do with a non-zero `report.exit_code()`; this
    function's contract is that the report is truthful about what it managed to
    read and what it could not.
    """
    report = heartbeat.RunReport(job="memory-review-collect")
    owns_store = store is None
    store = store or Store()
    layout = layout or config.discover_layout()

    traffic = TrafficLog()
    client = client or CMClient(traffic_log=traffic)
    traffic = client.traffic

    cursor_from = since or store.get_cursor(CURSOR_NAME) or _default_since()
    run_id = store.start_run("collect", cursor_from)
    client.run_id = run_id

    counters = {
        "conversations_seen": 0, "entries_fetched": 0,
        "utterances_extracted": 0, "utterances_new": 0,
        "memory_files_seen": 0, "memory_files_changed": 0,
        "memory_files_new": 0, "memory_files_removed": 0,
        "instruction_files_seen": 0, "instruction_passages": 0,
    }
    cursor_to: str | None = None
    fatal: str | None = None

    try:
        # --- Input assertions, before any work is trusted ---------------------
        corpus_ts = None
        try:
            corpus_ts, cm_health = client.corpus_freshness()
            report.assert_true(
                "cm_reachable", True,
                f"CM at {client.base_url} answered /health", "",
                observed=cm_health.get("status"))
            report.assert_fresh("cm_corpus_fresh", corpus_ts,
                                config.CORPUS_MAX_AGE_SECONDS,
                                severity=heartbeat.DEGRADED)
            report.count("cm_conversation_count", cm_health.get("conversationCount"))
            report.count("cm_entry_count", cm_health.get("conversationEntryCount"))
            scheduler = cm_health.get("scheduler") or {}
            if scheduler.get("lastRunStatus") not in (None, "success"):
                report.degrade(
                    f"CM ingest scheduler last run reported "
                    f"{scheduler.get('lastRunStatus')!r}")
        except CMError as exc:
            report.assert_true(
                "cm_reachable", False, "",
                f"CM unreachable at {client.base_url}: {exc}",
                severity=heartbeat.FAILED)

        report.assert_nonempty("instruction_surfaces_found", layout.surfaces)
        report.assert_nonempty("memory_dirs_found", layout.memory_dirs)
        report.assert_nonempty("okf_bundles_found", layout.bundles)

        # A failed assertion stops the CM pull. It does not stop the local
        # collection, because the local tiers are independent inputs and a packet
        # built from three of four sources beats no packet — but the run is
        # already marked degraded or failed and the cursor will not advance.
        cm_usable = all(
            a.status == heartbeat.OK for a in report.assertions
            if a.name in ("cm_reachable", "cm_corpus_fresh"))

        # --- 1. CM utterance corpus -------------------------------------------
        if cm_usable:
            cursor_to = utcnow()
            conversations = client.conversations_since(cursor_from)
            counters["conversations_seen"] = len(conversations)

            all_entries: list[dict] = []
            utterances: list[dict] = []
            for conversation in conversations:
                conv_id = conversation.get("id")
                if not isinstance(conv_id, int):
                    report.note(f"conversation without integer id skipped: "
                                f"{conversation.get('conversation_id')!r}")
                    continue
                for entry in client.conversation_entries(conv_id, role="user"):
                    all_entries.append(entry)
                    utterance = extract.extract_utterance(
                        entry, conversation=conversation)
                    if utterance:
                        utterances.append(utterance.as_row())

            counters["entries_fetched"] = len(all_entries)
            counters["utterances_extracted"] = len(utterances)
            counters["utterances_new"] = store.insert_utterances(run_id, utterances)
            report.count("extraction", extract.extraction_report(all_entries))

            # A window that returned conversations but no user entries at all is
            # a broken pull, not a quiet day.
            if counters["conversations_seen"] > 0 and counters["entries_fetched"] == 0:
                report.assert_true(
                    "entries_returned_for_conversations", False, "",
                    f"{counters['conversations_seen']} conversations since "
                    f"{cursor_from} returned zero user entries — the entries "
                    "endpoint is answering but empty",
                    severity=heartbeat.DEGRADED)
        else:
            report.note("CM pull skipped because an input assertion failed — "
                        "cursor NOT advanced, window will be re-read")

        # --- 2 & 3. Memory tiers ----------------------------------------------
        items = list(extract.collect_memory_items(layout))
        counters["memory_files_seen"] = len(items)
        report.assert_nonempty("memory_items_read", items)

        for item in items:
            verdict = store.upsert_memory_item(run_id, item.as_row())
            if verdict == "new":
                counters["memory_files_new"] += 1
                counters["memory_files_changed"] += 1
            elif verdict == "changed":
                counters["memory_files_changed"] += 1
            elif verdict != "unchanged":  # fail closed on an unknown verdict
                raise RuntimeError(f"upsert_memory_item returned {verdict!r}")

        counters["memory_files_removed"] = store.mark_missing_memory_items(
            run_id, ("auto-memory", "okf-concept"))

        # --- 4. The always-loaded surface -------------------------------------
        instruction_files = [f for surface in layout.surfaces
                             for f in surface.instruction_files()]
        counters["instruction_files_seen"] = len(instruction_files)
        report.assert_nonempty("instruction_files_read", instruction_files)

        passages = [p.as_row() for p in extract.segment_instructions(layout)]
        counters["instruction_passages"] = store.replace_instruction_passages(
            run_id, passages)
        report.assert_nonempty("instruction_passages_segmented", passages)

    except CMUnavailable as exc:
        fatal = f"CM became unreachable mid-run: {exc}"
        report.fail(fatal)
    except CMError as exc:
        fatal = f"CM request failed mid-run: {exc}"
        report.fail(fatal)
    except Exception as exc:  # noqa: BLE001 — an unexpected failure must be loud
        fatal = f"{type(exc).__name__}: {exc}"
        report.fail(fatal)
    finally:
        for key, value in counters.items():
            report.count(key, value)
        report.count("traffic", traffic.summary())
        if traffic.write_failures:
            report.degrade(
                f"{traffic.write_failures} CM traffic log write(s) failed — "
                "observability is degraded even though collection may have worked")
        try:
            store.record_traffic(traffic.records)
        except Exception as exc:  # noqa: BLE001
            report.degrade(f"traffic could not be written to the store: {exc}")

        status = report.status
        # The cursor advances only on a fully clean run.
        if status == heartbeat.OK and cursor_to:
            store.set_cursor(CURSOR_NAME, cursor_to)
            report.count("cursor_advanced_to", cursor_to)
        else:
            report.count("cursor_advanced_to", None)
            report.count("cursor_held_at", cursor_from)

        store.finish_run(
            run_id,
            status=status,
            cursor_to=cursor_to if status == heartbeat.OK else None,
            conversations_seen=counters["conversations_seen"],
            entries_fetched=counters["entries_fetched"],
            utterances_extracted=counters["utterances_extracted"],
            utterances_new=counters["utterances_new"],
            memory_files_seen=counters["memory_files_seen"],
            memory_files_changed=counters["memory_files_changed"],
            instruction_files_seen=counters["instruction_files_seen"],
            assertions_json=json.dumps([a.as_dict() for a in report.assertions]),
            notes="; ".join(report.notes) or None,
            error=fatal)

        if write_heartbeat:
            heartbeat.write(
                heartbeat_path or config.COLLECT_HEARTBEAT,
                report.as_dict({
                    "run_id": run_id,
                    "cursor_from": cursor_from,
                    "cursor_to": cursor_to if status == heartbeat.OK else None,
                    "corpus_total_utterances": store.utterance_count(),
                    "backend": "cm-http-api/v1",
                }))

        if owns_store:
            store.close()

    return report
