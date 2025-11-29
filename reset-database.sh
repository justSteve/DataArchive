#!/bin/bash
# Reset Database Script
# Backs up existing database and creates a fresh one

set -e  # Exit on error

DB_PATH="output/archive.db"
BACKUP_DIR="output/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

echo "=========================================="
echo "DataArchive Database Reset"
echo "=========================================="
echo ""

# Check if database exists
if [ -f "$DB_PATH" ]; then
    # Create backup directory if it doesn't exist
    mkdir -p "$BACKUP_DIR"

    BACKUP_PATH="$BACKUP_DIR/archive_backup_$TIMESTAMP.db"

    echo "📦 Backing up existing database..."
    cp "$DB_PATH" "$BACKUP_PATH"
    echo "   ✓ Backup created: $BACKUP_PATH"

    # Get database stats before deletion
    FILE_SIZE=$(du -h "$DB_PATH" | cut -f1)
    SCAN_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM scans" 2>/dev/null || echo "0")
    FILE_COUNT=$(sqlite3 "$DB_PATH" "SELECT SUM(file_count) FROM scans WHERE file_count IS NOT NULL" 2>/dev/null || echo "0")

    echo ""
    echo "📊 Database Statistics:"
    echo "   • Size: $FILE_SIZE"
    echo "   • Total Scans: $SCAN_COUNT"
    echo "   • Total Files: $FILE_COUNT"
    echo ""

    # Ask for confirmation
    read -p "Are you sure you want to delete the current database? (yes/no): " CONFIRM

    if [ "$CONFIRM" != "yes" ]; then
        echo ""
        echo "❌ Reset cancelled. Backup preserved at: $BACKUP_PATH"
        exit 0
    fi

    # Delete old database
    echo ""
    echo "🗑️  Deleting old database..."
    rm -f "$DB_PATH"
    echo "   ✓ Old database deleted"
else
    echo "ℹ️  No existing database found at $DB_PATH"
fi

# Create fresh database
echo ""
echo "🔨 Creating fresh database..."

# Activate virtual environment and initialize database
cd "$(dirname "$0")"

if [ ! -d "python/venv" ]; then
    echo "❌ Error: Python virtual environment not found at python/venv"
    echo "   Run: cd python && python3 -m venv venv && pip install -r requirements.txt"
    exit 1
fi

source python/venv/bin/activate

python3 -c "
import sys
sys.path.insert(0, 'python')
from core.database import Database
db = Database('$DB_PATH')
print('✓ Database schema initialized')
"

echo ""
echo "=========================================="
echo "✅ Database Reset Complete!"
echo "=========================================="
echo ""
echo "New database: $DB_PATH"

if [ -f "$BACKUP_PATH" ]; then
    echo "Backup saved: $BACKUP_PATH"
    echo ""
    echo "To restore backup:"
    echo "  cp $BACKUP_PATH $DB_PATH"
fi

echo ""
echo "You can now start scanning drives!"
echo ""
