#!/bin/bash
# Deploy Windows-side scripts to OneDrive Tools directory.
# Run from WSL after any changes to scripts/windows/*.ps1
#
# Usage:
#   ./scripts/shell/deploy-to-windows.sh
#   ./scripts/shell/deploy-to-windows.sh --dry-run

set -euo pipefail

SRC="$(cd "$(dirname "$0")/../.." && pwd)/scripts/windows"
DST="/mnt/c/Users/steve/OneDrive/Tools/DataArchiver"

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    echo "[DRY RUN]"
fi

# Ensure destination exists
if [[ "$DRY_RUN" == false ]]; then
    mkdir -p "$DST"
fi

copied=0
skipped=0

for src_file in "$SRC"/*.ps1 "$SRC"/*.bat; do
    [ -f "$src_file" ] || continue
    filename=$(basename "$src_file")
    dst_file="$DST/$filename"

    # Skip if destination is identical
    if [ -f "$dst_file" ] && cmp -s "$src_file" "$dst_file"; then
        skipped=$((skipped + 1))
        continue
    fi

    echo "  → $filename"
    if [[ "$DRY_RUN" == false ]]; then
        cp "$src_file" "$dst_file"
    fi
    copied=$((copied + 1))
done

echo ""
echo "Deployed: $copied files updated, $skipped unchanged"
echo "Target: $DST"
