#!/usr/bin/env bash
# memory-review-daily.sh — daily collection + packet build + desk page. [da-04r]
#
# Cron-side launcher for the CM-to-DataArchive memory review pipeline. Spawns no
# Claude session: the collection, the clustering and the packet build are
# deterministic Python. Judgement happens once, in front of Steve, on the form.
#
# Install (see docs/memory-review-pipeline.md for the full runbook):
#   15 23 * * *  /usr/bin/bash /root/projects/DataArchive/scripts/cron/memory-review-daily.sh
#
# 23:15 is chosen to sit after COO's 22:30 zepo pulse so the two do not contend
# for the box, and before the 06:30 corpus pull.
#
# Exit codes — cron and the operator both read these:
#   0  healthy
#   1  degraded: it ran, it wrote a heartbeat, some input assertion failed
#   2  failed:   it could not do its job
#
# There is no exit path that reports success without having written a heartbeat.
# A run that finds nothing writes `status: ok` with the counts it looked at; a
# run that never fires leaves the heartbeat's `ts` to go stale. Those are
# different states and `memory_review status` reports them differently.

set -uo pipefail

REPO_ROOT="${MR_REPO_ROOT:-/root/projects/DataArchive}"
PYTHON="${MR_PYTHON:-python3}"
LOG_DIR="${MR_LOG_DIR:-/var/moo/logs/memory-review}"
DATE="$(date -u +%Y-%m-%d)"
LOG="${LOG_DIR}/daily-${DATE}.log"

mkdir -p "$LOG_DIR" || {
    echo "FATAL: cannot create log directory $LOG_DIR" >&2
    exit 2
}

{
    echo "=== memory-review-daily start $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

    if [[ ! -d "$REPO_ROOT/python/memory_review" ]]; then
        echo "FATAL: package missing at $REPO_ROOT/python/memory_review"
        echo "       This is a broken checkout, not an empty day. Exiting 2 so the"
        echo "       failure is visible instead of looking like a quiet run."
        exit 2
    fi

    if ! command -v "$PYTHON" >/dev/null 2>&1; then
        echo "FATAL: $PYTHON not on PATH (cron PATH is minimal — set MR_PYTHON)"
        exit 2
    fi

    cd "$REPO_ROOT" || { echo "FATAL: cannot cd to $REPO_ROOT"; exit 2; }
    export PYTHONPATH="$REPO_ROOT/python${PYTHONPATH:+:$PYTHONPATH}"

    echo "--- collect ---"
    "$PYTHON" -m memory_review collect
    collect_rc=$?
    echo "collect rc=$collect_rc"

    # A failed collection still gets a packet built, because the packet is built
    # from the store and the store still holds yesterday's material. What it must
    # NOT do is look healthy: analyze.build asserts on the last collection's
    # status and degrades the packet accordingly, and the page carries a banner.
    if [[ $collect_rc -ge 2 ]]; then
        echo "WARNING: collection FAILED. Building a packet from existing store"
        echo "         contents anyway — it will be marked degraded and the desk"
        echo "         page will say so. Silence here would be the worse failure."
    fi

    echo "--- publish ---"
    "$PYTHON" -m memory_review publish
    publish_rc=$?
    echo "publish rc=$publish_rc"

    case "$publish_rc" in
        0) status="healthy" ;;
        1) status="degraded" ;;
        2) status="failed" ;;
        *) status="unknown-exit-${publish_rc}"; publish_rc=2 ;;  # fail closed
    esac

    rc=$(( collect_rc > publish_rc ? collect_rc : publish_rc ))
    echo "=== memory-review-daily end $(date -u +%Y-%m-%dT%H:%M:%SZ) "\
"(collect=$collect_rc publish=$publish_rc overall=$rc status=$status) ==="
    exit "$rc"
} >> "$LOG" 2>&1
