#!/usr/bin/env bash
# memory-review-weekly.sh — the scheduled sitting. [da-04r]
#
# The packet accumulates daily; this is the weekly appointment that puts it in
# front of Steve. It rebuilds the packet from the freshest collection, makes sure
# the capture endpoint is up BEFORE the page is opened, and only then opens the
# browser — because handing him a page whose Record button will fail is worse
# than not opening it at all (`.claude/rules/shared-executable-space.md`: prepare
# the endpoint, verify the target resolves, then present).
#
# Install:
#   30 16 * * 5  /usr/bin/bash /root/projects/DataArchive/scripts/cron/memory-review-weekly.sh
#
# Friday late-afternoon is a starting cadence, not a measured one — Steve moves
# it by editing the crontab line. What matters is that the window stays short
# enough that he still remembers the conversations the packet is drawn from.
#
# Exit codes: 0 opened · 1 opened degraded · 2 could not present it.
#
# `--no-open` builds and reports without touching the browser, for testing.

set -uo pipefail

REPO_ROOT="${MR_REPO_ROOT:-/root/projects/DataArchive}"
PYTHON="${MR_PYTHON:-python3}"
HOST="${MR_ENDPOINT_HOST:-127.0.0.1}"
PORT="${MR_ENDPOINT_PORT:-3010}"
LOG_DIR="${MR_LOG_DIR:-/var/moo/logs/memory-review}"
DESK_PAGE="${MR_DESK_PAGE:-/var/moo/desk/desk-memory-review.html}"
DATE="$(date -u +%Y-%m-%d)"
LOG="${LOG_DIR}/weekly-${DATE}.log"
OPEN=1

[[ "${1:-}" == "--no-open" ]] && OPEN=0

mkdir -p "$LOG_DIR" || { echo "FATAL: cannot create $LOG_DIR" >&2; exit 2; }

{
    echo "=== memory-review-weekly start $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

    cd "$REPO_ROOT" || { echo "FATAL: cannot cd to $REPO_ROOT"; exit 2; }
    export PYTHONPATH="$REPO_ROOT/python${PYTHONPATH:+:$PYTHONPATH}"

    echo "--- refresh packet ---"
    "$PYTHON" -m memory_review publish
    publish_rc=$?
    echo "publish rc=$publish_rc"

    if [[ $publish_rc -ge 2 ]]; then
        echo "FATAL: packet build failed. Not opening a page — there is nothing"
        echo "       trustworthy to review. Diagnose with:"
        echo "         cd $REPO_ROOT && PYTHONPATH=python $PYTHON -m memory_review status"
        exit 2
    fi

    echo "--- ensure capture endpoint ---"
    bash "$REPO_ROOT/scripts/cron/memory-review-endpoint.sh" supervise
    endpoint_rc=$?
    echo "endpoint supervise rc=$endpoint_rc"

    if [[ $endpoint_rc -ne 0 ]]; then
        echo "WARNING: the capture endpoint is NOT up. The page still opens and"
        echo "         still holds answers in the browser, and it will say in red"
        echo "         that nothing has been recorded. That is the honest state."
    fi

    if [[ ! -f "$DESK_PAGE" ]]; then
        echo "FATAL: desk page missing at $DESK_PAGE after a successful publish"
        exit 2
    fi

    if [[ $OPEN -eq 1 ]]; then
        echo "--- open ---"
        if command -v powershell.exe >/dev/null 2>&1; then
            powershell.exe Start-Process \
                "file://wsl.localhost/Zgent${DESK_PAGE}" >/dev/null 2>&1 \
                || echo "WARNING: powershell.exe Start-Process failed; open it by hand"
        else
            echo "WARNING: powershell.exe not on PATH — cannot open a Windows browser"
        fi
    fi

    echo "  desk page:  file://wsl.localhost/Zgent${DESK_PAGE}"
    echo "  served at:  http://${HOST}:${PORT}/review"

    rc=$(( endpoint_rc != 0 ? 1 : publish_rc ))
    case "$rc" in
        0|1|2) : ;;
        *) rc=2 ;;   # fail closed on anything unexpected
    esac
    echo "=== memory-review-weekly end $(date -u +%Y-%m-%dT%H:%M:%SZ) (rc=$rc) ==="
    exit "$rc"
} 2>&1 | tee -a "$LOG"

exit "${PIPESTATUS[0]}"
