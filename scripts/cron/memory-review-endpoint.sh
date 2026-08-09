#!/usr/bin/env bash
# memory-review-endpoint.sh — lifecycle for the decision capture endpoint. [da-04r]
#
#   memory-review-endpoint.sh start|stop|restart|status|supervise
#
# `supervise` is the cron entry point: it starts the endpoint if it is not
# listening and does nothing if it is. Run it every five minutes so a reboot or a
# crash self-heals without anyone noticing it happened — and so the endpoint
# heartbeat never goes stale while the box is up.
#
#   */5 * * * * /usr/bin/bash /root/projects/DataArchive/scripts/cron/memory-review-endpoint.sh supervise
#
# Why a supervisor and not systemd: this box's proven convention is cron wrapper
# plus /var/moo/state heartbeat plus a staleness check. Adding a second
# observability convention for one process means inheriting a second set of
# failure modes. Independently restartable and independently observable wins.
#
# Exit codes: 0 running (or started) · 1 not running when it should be · 2 error.

set -uo pipefail

REPO_ROOT="${MR_REPO_ROOT:-/root/projects/DataArchive}"
PYTHON="${MR_PYTHON:-python3}"
HOST="${MR_ENDPOINT_HOST:-127.0.0.1}"
PORT="${MR_ENDPOINT_PORT:-3010}"
LOG_DIR="${MR_LOG_DIR:-/var/moo/logs/memory-review}"
RUN_DIR="${MR_RUN_DIR:-/var/moo/state}"
PIDFILE="${RUN_DIR}/memory-review-endpoint.pid"
LOG="${LOG_DIR}/endpoint.log"

mkdir -p "$LOG_DIR" "$RUN_DIR" || {
    echo "FATAL: cannot create $LOG_DIR or $RUN_DIR" >&2
    exit 2
}

_log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG" >&2; }

is_listening() {
    curl -s -m 5 -o /dev/null -w '%{http_code}' \
        "http://${HOST}:${PORT}/api/health" 2>/dev/null | grep -q '^200$'
}

running_pid() {
    [[ -f "$PIDFILE" ]] || return 1
    local pid
    pid="$(cat "$PIDFILE" 2>/dev/null)"
    [[ -n "$pid" ]] || return 1
    kill -0 "$pid" 2>/dev/null || return 1
    printf '%s' "$pid"
}

do_start() {
    if is_listening; then
        _log "already listening on ${HOST}:${PORT} — nothing to do"
        return 0
    fi
    if [[ ! -d "$REPO_ROOT/python/memory_review" ]]; then
        _log "FATAL: package missing at $REPO_ROOT/python/memory_review"
        return 2
    fi
    if ! command -v "$PYTHON" >/dev/null 2>&1; then
        _log "FATAL: $PYTHON not on PATH (cron PATH is minimal — set MR_PYTHON)"
        return 2
    fi

    cd "$REPO_ROOT" || { _log "FATAL: cannot cd to $REPO_ROOT"; return 2; }
    PYTHONPATH="$REPO_ROOT/python${PYTHONPATH:+:$PYTHONPATH}" \
        nohup "$PYTHON" -m memory_review serve --host "$HOST" --port "$PORT" \
        >> "$LOG" 2>&1 &
    local pid=$!
    echo "$pid" > "$PIDFILE"
    _log "started pid $pid on ${HOST}:${PORT}"

    # Confirm it actually came up. Starting a process and declaring victory is
    # how a dead service hides behind a green log line.
    local attempt
    for attempt in 1 2 3 4 5 6 7 8 9 10; do
        sleep 1
        if is_listening; then
            _log "confirmed healthy after ${attempt}s"
            return 0
        fi
        if ! kill -0 "$pid" 2>/dev/null; then
            _log "FATAL: pid $pid exited during startup — see $LOG"
            rm -f "$PIDFILE"
            return 2
        fi
    done
    _log "FATAL: pid $pid is alive but /api/health did not answer within 10s"
    return 2
}

do_stop() {
    local pid
    if pid="$(running_pid)"; then
        kill "$pid" 2>/dev/null
        sleep 1
        kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null
        _log "stopped pid $pid"
    else
        _log "no running pid recorded"
    fi
    rm -f "$PIDFILE"
    return 0
}

do_status() {
    if is_listening; then
        echo "memory-review endpoint: LISTENING on http://${HOST}:${PORT}"
        curl -s -m 5 "http://${HOST}:${PORT}/api/health" || true
        echo
        return 0
    fi
    echo "memory-review endpoint: NOT LISTENING on http://${HOST}:${PORT}"
    echo "  Decisions made on the desk page are held in the browser until this"
    echo "  is up. Start it with: $0 start"
    return 1
}

case "${1:-supervise}" in
    start)      do_start; exit $? ;;
    stop)       do_stop; exit $? ;;
    restart)    do_stop; do_start; exit $? ;;
    status)     do_status; exit $? ;;
    supervise)
        if is_listening; then
            exit 0
        fi
        _log "not listening — supervising a restart"
        do_start
        exit $?
        ;;
    *)
        # Fail closed on an unrecognised verb rather than defaulting to something
        # that looks like it worked.
        echo "unknown command '${1}'; expected start|stop|restart|status|supervise" >&2
        exit 2
        ;;
esac
