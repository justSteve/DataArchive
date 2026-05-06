#!/bin/bash
# Prioritized rescue copy from degraded NAS drive to dock I:.
# Uses ddrescue per-file for resilience against bad sectors.
# Resumable — Ctrl+C and restart picks up where it left off.
#
# Prerequisites:
#   1. NAS drive attached: wsl --mount \\.\PHYSICALDRIVE2 --bare
#   2. Dock powered on with NASR drive as I:
#   3. gddrescue installed: apt install gddrescue
#
# Usage:  bash Harvester/copy-nas-to-dock.sh [--retry]
#   --retry : re-attempt previously failed blocks (slow, thorough)

set -uo pipefail

SRC="/mnt/nas/shares"
DST="/mnt/i/OldNAS"
NAS_DEV="/dev/sdf4"
NAS_MNT="/mnt/nas"
LOGDIR="$DST/.rescue-logs"
MAPDIR="$DST/.rescue-maps"
MANIFEST="/tmp/nas-rescue-manifest.txt"
RETRY=false

[[ "${1:-}" == "--retry" ]] && RETRY=true

# --- Pre-flight checks ---
if ! lsblk "$NAS_DEV" &>/dev/null; then
    echo "ERROR: $NAS_DEV not found."
    echo "  Run from elevated PowerShell:  wsl --mount \\\\.\\PHYSICALDRIVE2 --bare"
    exit 1
fi

if ! mountpoint -q "$NAS_MNT"; then
    echo "Mounting NAS partition read-only..."
    sudo mkdir -p "$NAS_MNT"
    sudo mount -o ro "$NAS_DEV" "$NAS_MNT"
fi

if [ ! -d /mnt/i ]; then
    echo "ERROR: I: not accessible at /mnt/i"
    exit 1
fi

if ! command -v ddrescue &>/dev/null; then
    echo "ERROR: ddrescue not found. Install: apt install gddrescue"
    exit 1
fi

mkdir -p "$DST" "$LOGDIR" "$MAPDIR"

# --- Skip list: NAS firmware artifacts (no original content) ---
is_skippable() {
    local f="$1"
    case "$f" in
        .wdmc/*|*/.wdmc/*)             return 0 ;;
        .wdphotos/*|*/.wdphotos/*)     return 0 ;;
        .groupingDb/*|*/.groupingDb/*) return 0 ;;
        */Folder.jpg)                  return 0 ;;
        */AlbumArt_*.jpg)              return 0 ;;
        *)                             return 1 ;;
    esac
}

# --- Priority assignment ---
# Returns 1-3 (lower = more important)
file_priority() {
    local f="$1"
    case "$f" in
        # P1: Irreplaceable personal data
        */am.steve/*)            echo 1 ;;
        */BackupOneDrive/*)      echo 1 ;;
        */GMailTakeouts/*)       echo 1 ;;
        */Paula/*)               echo 1 ;;
        */Shared\ Pictures/*)   echo 1 ;;
        */Desktop/*)             echo 1 ;;
        */Documents/*)           echo 1 ;;
        */PhonePhotos/*)         echo 1 ;;
        # P3: Large replaceable media (checked before P2 catch-all)
        */Downloads/*.mp4)       echo 3 ;;
        */Downloads/*.MP4)       echo 3 ;;
        */Shared\ Videos/*)     echo 3 ;;
        */Shared\ Music/*)      echo 3 ;;
        */speedtest/*)           echo 3 ;;
        */twonky/*)              echo 3 ;;
        */SmartWare/*)           echo 3 ;;
        */TimeMachineBackup/*)   echo 3 ;;
        # P2: Everything else (code, backups, config, misc)
        *)                       echo 2 ;;
    esac
}

# --- Build manifest of missing files ---
echo "=== NAS Rescue Copy ==="
echo ""

SCAN_TIMEOUT=300  # 5 minutes max for source scan — drive is degraded

# Enumerate dest files (fast — local NTFS)
find "$DST" -not -path "$DST/.rescue-*" -type f -printf '%s\t%P\n' 2>/dev/null > /tmp/nas-dst-list.txt
dst_count=$(wc -l < /tmp/nas-dst-list.txt)
echo "Dest:   $dst_count files already on dock"

# Enumerate source files (slow — degraded drive, timeout protected)
echo "Scanning source (${SCAN_TIMEOUT}s timeout — drive is degraded)..."
timeout "$SCAN_TIMEOUT" find "$SRC" -type f -printf '%s\t%P\n' 2>/dev/null > /tmp/nas-src-list.txt
scan_rc=$?
src_count=$(wc -l < /tmp/nas-src-list.txt)

if [[ $scan_rc -eq 124 ]]; then
    echo "Source: $src_count files (PARTIAL — scan timed out after ${SCAN_TIMEOUT}s)"
    echo "  Some directories unreachable due to drive degradation."
    echo "  Known missing files will still be attempted."
    PARTIAL_SCAN=true
else
    echo "Source: $src_count files (complete)"
    PARTIAL_SCAN=false
fi

# Build lookup of dest files: path→size
declare -A dest_sizes
while IFS=$'\t' read -r dsize dpath; do
    dest_sizes["$dpath"]="$dsize"
done < /tmp/nas-dst-list.txt

# Find files missing or different-sized on dest
> "$MANIFEST"
skipped_artifacts=0
while IFS=$'\t' read -r src_size src_path; do
    if is_skippable "$src_path"; then
        ((skipped_artifacts++))
        continue
    fi
    dst_size="${dest_sizes["$src_path"]:-}"
    if [[ -z "$dst_size" || "$dst_size" != "$src_size" ]]; then
        pri=$(file_priority "$src_path")
        printf '%d\t%s\t%s\n' "$pri" "$src_size" "$src_path" >> "$MANIFEST"
    fi
done < /tmp/nas-src-list.txt
unset dest_sizes

# Append known missing files not found by scan (drive too degraded to enumerate)
append_if_missing() {
    local size="$1" path="$2"
    if ! grep -qF "$path" "$MANIFEST" 2>/dev/null; then
        if timeout 30 test -f "$SRC/$path" 2>/dev/null; then
            pri=$(file_priority "$path")
            printf '%d\t%s\t%s\n' "$pri" "$size" "$path" >> "$MANIFEST"
        fi
    fi
}
# Known missing from Steve/Backups/Steve/Downloads (verified 2026-05-05)
append_if_missing 3993690654 "Steve/Backups/Steve/Downloads/Marrage2.mp4"
append_if_missing 434304046  "Steve/Backups/Steve/Downloads/R.Starr Threesome Addiction - 480p.mp4"
append_if_missing 1105644195 "Steve/Backups/Steve/Downloads/Scene 2 From All Natural Babes No 3 - 1080p.mp4"
append_if_missing 1145049890 "Steve/Backups/Steve/Downloads/Scene 8 From All Natural Babes No 3 - 1080p.mp4"
append_if_missing 6453021280 "Steve/Backups/Steve/Downloads/Ultimate MILF Fantasies - 1080p.mp4"
append_if_missing 282        "Steve/Backups/Steve/Downloads/desktop.ini"
append_if_missing 282        "Public/Shared Pictures/desktop.ini"

# Sort by priority then size (smallest first within tier)
sort -t$'\t' -k1,1n -k2,2n "$MANIFEST" > "${MANIFEST}.sorted"
mv "${MANIFEST}.sorted" "$MANIFEST"

missing=$(wc -l < "$MANIFEST")
missing_bytes=$(awk -F'\t' '{s+=$2} END {print s}' "$MANIFEST")
missing_human=$(numfmt --to=iec-i --suffix=B "$missing_bytes" 2>/dev/null || echo "${missing_bytes} bytes")

echo ""
echo "Missing: $missing files ($missing_human)"
echo "Skipped: $skipped_artifacts NAS firmware artifacts (.wdmc, .wdphotos, .groupingDb)"
if [[ "$PARTIAL_SCAN" == true ]]; then
    echo "  ⚠ Partial scan — actual total may be higher"
fi
echo ""

# Show tier summary
for p in 1 2 3; do
    tier_count=$(awk -F'\t' -v p="$p" '$1==p' "$MANIFEST" | wc -l)
    tier_bytes=$(awk -F'\t' -v p="$p" '$1==p {s+=$2} END {print s+0}' "$MANIFEST")
    tier_human=$(numfmt --to=iec-i --suffix=B "$tier_bytes" 2>/dev/null || echo "${tier_bytes} bytes")
    label="P$p"
    case $p in
        1) label="P1 (irreplaceable)" ;;
        2) label="P2 (valuable)" ;;
        3) label="P3 (replaceable media)" ;;
    esac
    echo "  $label: $tier_count files, $tier_human"
done

echo ""
echo "Starting rescue copy... (Ctrl+C to pause, re-run to resume)"
echo "==========================================================="
echo ""

# --- Rescue copy ---
copied=0
failed=0
skipped=0

while IFS=$'\t' read -r pri file_size rel_path; do
    src_file="$SRC/$rel_path"
    dst_file="$DST/$rel_path"
    map_name=$(echo "$rel_path" | tr '/' '_' | tr ' ' '_')
    map_file="$MAPDIR/${map_name}.map"

    # Skip if dest already has correct size (raced by prior run)
    if [[ -f "$dst_file" ]]; then
        actual=$(stat -c%s "$dst_file" 2>/dev/null || echo 0)
        if [[ "$actual" == "$file_size" ]]; then
            ((skipped++))
            continue
        fi
    fi

    # Create dest directory
    mkdir -p "$(dirname "$dst_file")"

    # ddrescue flags
    dd_flags="-f"
    if [[ "$RETRY" == false ]]; then
        dd_flags="$dd_flags -n"  # first pass: skip bad blocks
    fi

    size_human=$(numfmt --to=iec-i --suffix=B "$file_size" 2>/dev/null || echo "${file_size}B")
    echo "[P${pri}] ${size_human}  ${rel_path}"

    if ddrescue $dd_flags "$src_file" "$dst_file" "$map_file" >> "$LOGDIR/rescue.log" 2>&1; then
        actual=$(stat -c%s "$dst_file" 2>/dev/null || echo 0)
        if [[ "$actual" == "$file_size" ]]; then
            echo "       ✓ complete"
            ((copied++))
            rm -f "$map_file"  # clean up mapfile on success
        else
            echo "       ~ partial ($actual / $file_size bytes)"
            ((failed++))
        fi
    else
        echo "       ✗ failed (see $LOGDIR/rescue.log)"
        ((failed++))
    fi

done < "$MANIFEST"

echo ""
echo "==========================================================="
echo "Rescue complete."
echo "  Copied:  $copied"
echo "  Partial: $failed  (re-run with --retry to scrape bad blocks)"
echo "  Skipped: $skipped (already present)"
echo ""
echo "Logs:     $LOGDIR/rescue.log"
echo "Mapfiles: $MAPDIR/ (for partial files)"
