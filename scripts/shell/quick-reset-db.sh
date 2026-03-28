#!/bin/bash
# Quick Database Reset (No confirmation, for development)
# Creates backup automatically

set -e

DB_PATH="data/archive.db"
BACKUP_DIR="output/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

echo "🔄 Quick Database Reset..."

# Backup if exists
if [ -f "$DB_PATH" ]; then
    mkdir -p "$BACKUP_DIR"
    BACKUP_PATH="$BACKUP_DIR/archive_backup_$TIMESTAMP.db"
    cp "$DB_PATH" "$BACKUP_PATH"
    echo "✓ Backup: $BACKUP_PATH"
    rm -f "$DB_PATH"
fi

# Create fresh database (works on both Windows and Linux)
python -c "
import sys
sys.path.insert(0, 'python')
from core.database import Database
Database('$DB_PATH')
"

echo "✅ Database reset complete!"
echo "   Path: $DB_PATH"
