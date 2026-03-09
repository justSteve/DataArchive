#!/usr/bin/env python
"""Export duplicate files to CSV with full metadata."""
import sys
sys.path.insert(0, 'python')

import sqlite3
import csv
from datetime import datetime
from pathlib import Path

def export_duplicates_csv(output_file='output/duplicates_report.csv'):
    """Export all duplicate files to CSV with metadata."""

    conn = sqlite3.connect('output/archive.db')
    cursor = conn.cursor()

    # Find all files that have duplicates (same hash, multiple files)
    query = """
    WITH duplicate_hashes AS (
        SELECT hash_value
        FROM file_hashes
        WHERE hash_type = 'quick_hash'
        GROUP BY hash_value
        HAVING COUNT(DISTINCT file_id) > 1
    )
    SELECT
        f.file_id,
        f.scan_id,
        s.mount_point as drive_letter,
        fh.hash_value,
        f.path,
        f.size_bytes,
        f.modified_date,
        f.created_date,
        f.accessed_date,
        d.model as drive_model,
        d.serial_number as drive_serial
    FROM files f
    JOIN file_hashes fh ON f.file_id = fh.file_id AND fh.hash_type = 'quick_hash'
    JOIN duplicate_hashes dh ON fh.hash_value = dh.hash_value
    JOIN scans s ON f.scan_id = s.scan_id
    JOIN drives d ON s.drive_id = d.drive_id
    ORDER BY fh.hash_value, f.size_bytes DESC, s.mount_point, f.path
    """

    print("Querying database for duplicates...")
    cursor.execute(query)
    rows = cursor.fetchall()

    print(f"Found {len(rows):,} duplicate file instances")

    # Write to CSV
    print(f"Writing to {output_file}...")
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)

        # Header
        writer.writerow([
            'file_id',
            'scan_id',
            'drive_letter',
            'hash',
            'filename',
            'full_path',
            'size_bytes',
            'size_mb',
            'modified_date',
            'created_date',
            'accessed_date',
            'attributes',
            'drive_model',
            'drive_serial'
        ])

        # Data rows
        for row in rows:
            file_id, scan_id, drive_letter, hash_val, file_path, \
                file_size, modified, created, accessed, drive_model, drive_serial = row

            size_mb = file_size / (1024 * 1024) if file_size else 0
            filename = Path(file_path).name if file_path else ''

            writer.writerow([
                file_id,
                scan_id,
                drive_letter,
                hash_val,
                filename,
                file_path,
                file_size,
                f'{size_mb:.2f}',
                modified,
                created,
                accessed,
                '',  # attributes not in schema
                drive_model,
                drive_serial
            ])

    conn.close()

    print(f"\nExport complete!")
    print(f"Report saved to: {output_file}")

    # Print summary statistics
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            COUNT(DISTINCT fh.hash_value) as unique_hashes,
            COUNT(*) as total_instances,
            SUM(f.size_bytes) / (1024.0 * 1024 * 1024) as total_gb
        FROM files f
        JOIN file_hashes fh ON f.file_id = fh.file_id AND fh.hash_type = 'quick_hash'
        WHERE fh.hash_value IN (
            SELECT hash_value
            FROM file_hashes
            WHERE hash_type = 'quick_hash'
            GROUP BY hash_value
            HAVING COUNT(DISTINCT file_id) > 1
        )
    """)
    unique, total, total_gb = cursor.fetchone()

    # Wasted space = total space - space needed for one copy of each unique file
    avg_file_size_gb = total_gb / total if total > 0 else 0
    wasted_gb = total_gb - (unique * avg_file_size_gb)

    print(f"\nSummary:")
    print(f"  Unique duplicate groups: {unique:,}")
    print(f"  Total duplicate instances: {total:,}")
    print(f"  Total space used: {total_gb:.2f} GB")
    print(f"  Estimated wasted space: {wasted_gb:.2f} GB")

    return output_file

if __name__ == '__main__':
    export_duplicates_csv()
