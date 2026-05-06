#!/bin/bash
# Status check for copy-nas-to-dock.sh rescue operation.
# Usage: bash Harvester/rescue-status.sh

DST="/mnt/i/OldNAS"
LOGDIR="$DST/.rescue-logs"
MAPDIR="$DST/.rescue-maps"
MANIFEST="/tmp/nas-rescue-manifest.txt"

# Is the rescue running?
pid=$(pgrep -f "copy-nas-to-dock.sh" 2>/dev/null | head -1)
dd_pid=$(pgrep -f "ddrescue.*OldNAS" 2>/dev/null | head -1)

if [[ -n "$pid" ]]; then
    echo "Status: RUNNING (pid $pid)"
    if [[ -n "$dd_pid" ]]; then
        current=$(tr '\0' ' ' < /proc/"$dd_pid"/cmdline 2>/dev/null | grep -oP '(?<=shares/)\S+(?= /mnt)')
        [[ -n "$current" ]] && echo "Active: $current"
    fi
else
    echo "Status: NOT RUNNING"
fi
echo ""

# Progress from manifest
if [[ ! -f "$MANIFEST" ]]; then
    echo "No manifest found. Has the rescue been started?"
    exit 0
fi

python3 -c "
import os, sys

manifest = '$MANIFEST'
dst = '$DST'

done = 0; done_bytes = 0
partial = 0; partial_bytes_left = 0
waiting = 0; waiting_bytes = 0
tiers = {1:{'d':0,'w':0,'db':0,'wb':0}, 2:{'d':0,'w':0,'db':0,'wb':0}, 3:{'d':0,'w':0,'db':0,'wb':0}}

with open(manifest) as f:
    for line in f:
        parts = line.strip().split('\t', 2)
        if len(parts) != 3: continue
        pri, size_s, path = int(parts[0]), int(parts[1]), parts[2]
        dst_path = os.path.join(dst, path)
        if os.path.exists(dst_path):
            actual = os.path.getsize(dst_path)
            if actual == pri or actual == int(size_s):
                pass
            if actual >= int(size_s):
                done += 1; done_bytes += int(size_s)
                tiers[pri]['d'] += 1; tiers[pri]['db'] += int(size_s)
            else:
                partial += 1; partial_bytes_left += int(size_s) - actual
                tiers[pri]['w'] += 1; tiers[pri]['wb'] += int(size_s) - actual
        else:
            waiting += 1; waiting_bytes += int(size_s)
            tiers[pri]['w'] += 1; tiers[pri]['wb'] += int(size_s)

total = done + partial + waiting
def h(b):
    if b >= 1073741824: return f'{b/1073741824:.1f} GB'
    if b >= 1048576: return f'{b/1048576:.0f} MB'
    if b >= 1024: return f'{b/1024:.0f} KB'
    return f'{b} B'

pct = done * 100 // max(total, 1)
bar_w = 30
filled = pct * bar_w // 100
bar = '█' * filled + '░' * (bar_w - filled)
print(f'[{bar}] {pct}%  ({done}/{total} files)')
print(f'  Done:    {done:>6} files  {h(done_bytes):>10}')
print(f'  Partial: {partial:>6} files  {h(partial_bytes_left):>10} left')
print(f'  Waiting: {waiting:>6} files  {h(waiting_bytes):>10}')
print()
labels = {1: 'P1 irreplaceable', 2: 'P2 valuable', 3: 'P3 media'}
for p in [1, 2, 3]:
    t = tiers[p]
    tot_t = t['d'] + t['w']
    if tot_t == 0: continue
    tp = t['d'] * 100 // tot_t
    print(f'  {labels[p]:>20}: {t[\"d\"]}/{tot_t} done ({tp}%), {h(t[\"wb\"])} left')
"

# Mapfiles = files with unrecovered bad sectors
maps=$(ls "$MAPDIR"/*.map 2>/dev/null | wc -l)
if [[ $maps -gt 0 ]]; then
    echo ""
    echo "Mapfiles: $maps (files with bad sectors — re-run with --retry)"
    ls -1 "$MAPDIR"/*.map 2>/dev/null | head -5 | sed 's|.*/||; s|\.map$||; s|_|/|g'
    [[ $maps -gt 5 ]] && echo "  ... and $((maps - 5)) more"
fi

# Log tail
if [[ -f "$LOGDIR/rescue.log" ]]; then
    echo ""
    echo "Last log activity:"
    log_size=$(stat -c%s "$LOGDIR/rescue.log" 2>/dev/null || echo 0)
    log_human=$(numfmt --to=iec-i --suffix=B "$log_size" 2>/dev/null || echo "${log_size}B")
    log_age=$(stat -c%Y "$LOGDIR/rescue.log" 2>/dev/null || echo 0)
    now=$(date +%s)
    mins=$(( (now - log_age) / 60 ))
    echo "  Log size: $log_human, last write: ${mins}m ago"
fi
