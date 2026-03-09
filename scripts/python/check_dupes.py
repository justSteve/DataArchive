import sqlite3
import sys
from pathlib import Path

# Add python directory to path for logger import
sys.path.insert(0, str(Path(__file__).parent / 'python'))
from core.logger import get_logger

logger = get_logger(__name__)

try:
    conn = sqlite3.connect('output/archive.db')
    cursor = conn.cursor()
except sqlite3.Error as e:
    logger.error(f"Failed to connect to database: {e}", exc_info=True)
    sys.exit(1)

logger.info("Finding duplicate file candidates by size for scan_id 3")

try:
    # Find files with duplicate sizes
    cursor.execute('''
        SELECT size_bytes, COUNT(*) as count
        FROM files
        WHERE scan_id = 3 AND size_bytes > 1024
        GROUP BY size_bytes
        HAVING COUNT(*) > 1
        ORDER BY size_bytes * (COUNT(*) - 1) DESC
        LIMIT 20
    ''')
except sqlite3.Error as e:
    logger.error(f"Failed to query duplicate candidates: {e}", exc_info=True)
    conn.close()
    sys.exit(1)

results = cursor.fetchall()
logger.info(f"Found {len(results)} size groups with duplicates")
print('Top duplicate candidates on Z: (by size):')
print(f'{"Size (MB)":>12} | {"Count":>6} | {"Wasted (MB)":>12}')
print('-' * 40)

total_wasted = 0
for size, count in results:
    size_mb = size / (1024*1024)
    wasted_mb = size_mb * (count - 1)
    total_wasted += wasted_mb
    print(f'{size_mb:12.2f} | {count:6d} | {wasted_mb:12.2f}')

print(f'\nTotal potential wasted space in top 20: {total_wasted:.2f} MB')
logger.info(f"Total wasted space in top 20 groups: {total_wasted:.2f} MB")

# Get summary stats
try:
    cursor.execute('''
    SELECT
        COUNT(DISTINCT size_bytes) as unique_sizes_with_dupes,
        SUM(dup_count) as total_duplicate_files
    FROM (
        SELECT size_bytes, COUNT(*) - 1 as dup_count
        FROM files
        WHERE scan_id = 3 AND size_bytes > 1024
        GROUP BY size_bytes
        HAVING COUNT(*) > 1
    )
    ''')
except sqlite3.Error as e:
    logger.error(f"Failed to query summary statistics: {e}", exc_info=True)
    conn.close()
    sys.exit(1)

stats = cursor.fetchone()
print(f'\nSummary:')
print(f'  File sizes with duplicates: {stats[0]:,}')
print(f'  Total duplicate files: {stats[1]:,}')

logger.info(f"Summary: {stats[0]:,} file sizes with duplicates, {stats[1]:,} total duplicate files")

try:
    conn.close()
    logger.debug("Database connection closed")
except Exception as e:
    logger.warning(f"Error closing database connection: {e}")
