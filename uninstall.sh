#!/bin/bash

# DataArchive Uninstallation Script
# Removes the virtual environment and launcher
# Similar to uninstalling via Control Panel in Windows

set -e  # Exit on any error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
APP_NAME="dataarchive"
LAUNCHER="$SCRIPT_DIR/$APP_NAME"

echo "========================================"
echo "DataArchive Uninstallation"
echo "========================================"
echo ""

# Remove virtual environment
if [ -d "$VENV_DIR" ]; then
    echo "Removing virtual environment..."
    rm -rf "$VENV_DIR"
    echo "✓ Virtual environment removed"
else
    echo "No virtual environment found (already clean)"
fi

# Remove launcher script
if [ -f "$LAUNCHER" ]; then
    echo "Removing launcher script..."
    rm "$LAUNCHER"
    echo "✓ Launcher removed"
else
    echo "No launcher found (already clean)"
fi

# Note: We keep the data files (storage/, reports/) and source code
echo ""
echo "========================================"
echo "Uninstallation Complete!"
echo "========================================"
echo ""
echo "Note: Your data files, reports, and source code have been preserved."
echo "To reinstall, run: ./install.sh"
echo ""
