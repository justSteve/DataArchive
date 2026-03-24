#!/usr/bin/env python3
"""
Import Windows-native scan results (CSV + metadata JSON) into archive.db

Usage:
    python import_windows_scan.py D --label XXXX
    python import_windows_scan.py I --label OCL
"""

import sys
import json
import csv
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime

def main():
    parser = argparse.ArgumentParser(description='Import Windows scan into archive.db')
    parser.add_argument('drive_letter', help='Drive letter that was scanned (e.g., D)')
    parser.add_argument('--label', help='Drive label (4 char code)')
    parser.add_argument('--db', default='output/archive.db', help='Database path')
    parser.add_argument('--scan-dir', default='/mnt/c/DataArchive', help='Where scan-X.csv and meta-X.json live')
    args = parser.parse_args()

    dl = args.drive_letter.strip(':').upper()
    scan_dir = Path(args.scan_dir)
    csv_file = scan_dir / f'scan-{dl}.csv'
    meta_file = scan_dir / f'meta-{dl}.json'

    if not csv_file.exists():
        print(f"ERROR: {csv_file} not found")
        return 1
    if not meta_file.exists():
        print(f"ERROR: {meta_file} not found")
        return 1

    # Load metadata
    with open(meta_file, encoding='utf-8') as f:
        meta = json.load(f)

    print(f"Importing {dl}: {meta.get('model', '?')} (S/N: {meta.get('serial', '?')})")
    print(f"  Size: {(meta.get('size_bytes') or 0) / (1024**3):.1f} GB")
    print(f"  FS: {meta.get('filesystem')}, Label: {meta.get('label')}")
    if meta.get('os_product'):
        print(f"  OS: {meta.get('os_product')} build {meta.get('os_build')}")

    conn = sqlite3.connect(args.db)

    # Check if this drive serial already exists
    serial = meta.get('serial', f'UNKNOWN_{dl}')
    existing = conn.execute('SELECT drive_id FROM drives WHERE serial_number = ?', (serial,)).fetchone()

    label = args.label or meta.get('label') or dl
    drive_code = label

    if existing:
        drive_id = existing[0]
        # Update with better info
        conn.execute('''UPDATE drives SET
            model = ?, size_bytes = ?, filesystem = ?, partition_scheme = ?,
            label = ?, connection_type = ?, firmware_version = ?, bus_type = ?,
            drive_code = ?, last_scanned = ?, notes = COALESCE(notes, '') || ?
            WHERE drive_id = ?''',
            (meta.get('model'), meta.get('size_bytes'), meta.get('filesystem'),
             meta.get('partition_style'), label, meta.get('bus_type'),
             meta.get('firmware'), meta.get('bus_type'), drive_code,
             datetime.now().isoformat(),
             f"\nRescanned {datetime.now().isoformat()[:10]} via Windows-native scanner.",
             drive_id))
        print(f"  Updated existing drive_id {drive_id}")
    else:
        os_note = ''
        if meta.get('os_product'):
            os_note = f"{meta.get('os_product')} build {meta.get('os_build')} installed {meta.get('os_install_date', 'unknown')[:10] if meta.get('os_install_date') else 'unknown'}. "
        if meta.get('os_owner'):
            os_note += f"Owner: {meta.get('os_owner')}. "

        conn.execute('''INSERT INTO drives
            (serial_number, model, size_bytes, filesystem, partition_scheme, label,
             connection_type, firmware_version, bus_type, drive_code, notes, first_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (serial, meta.get('model'), meta.get('size_bytes'), meta.get('filesystem'),
             meta.get('partition_style'), label, meta.get('bus_type'),
             meta.get('firmware'), meta.get('bus_type'), drive_code,
             os_note, datetime.now().isoformat()))
        drive_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        print(f"  Created drive_id {drive_id}")

    # Start scan session
    scan_id = conn.execute('''INSERT INTO scans (drive_id, scan_path, status, started_at)
        VALUES (?, ?, 'IN_PROGRESS', ?)''',
        (drive_id, f'{dl}:\\', datetime.now().isoformat())).lastrowid
    print(f"  Scan session {scan_id}")

    # Import files from CSV
    file_count = 0
    total_size = 0
    batch = []
    batch_size = 5000

    with open(csv_file, encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            try:
                size = int(row.get('size_bytes', 0))
                batch.append((
                    scan_id,
                    row['path'],
                    size,
                    row.get('modified'),
                    row.get('created'),
                    row.get('accessed'),
                    row.get('extension', ''),
                    int(row.get('is_hidden', 0)),
                    int(row.get('is_system', 0)),
                    'medium'  # priority
                ))
                file_count += 1
                total_size += size

                if len(batch) >= batch_size:
                    conn.executemany('''INSERT INTO files
                        (scan_id, path, size_bytes, modified_date, created_date, accessed_date,
                         extension, is_hidden, is_system, priority)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', batch)
                    conn.commit()
                    batch = []
                    if file_count % 50000 == 0:
                        print(f"  {file_count:,} files imported...")
            except Exception as e:
                print(f"  WARN: skipping row: {e}")

    if batch:
        conn.executemany('''INSERT INTO files
            (scan_id, path, size_bytes, modified_date, created_date, accessed_date,
             extension, is_hidden, is_system, priority)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', batch)

    # Complete scan
    conn.execute('''UPDATE scans SET status = 'COMPLETE', file_count = ?,
        total_size_bytes = ?, completed_at = ? WHERE scan_id = ?''',
        (file_count, total_size, datetime.now().isoformat(), scan_id))
    conn.execute('''UPDATE drives SET last_scanned = ? WHERE drive_id = ?''',
        (datetime.now().isoformat(), drive_id))
    conn.commit()
    conn.close()

    print(f"\nDone: {file_count:,} files, {total_size / (1024**3):.2f} GB imported as scan {scan_id}")

if __name__ == '__main__':
    sys.exit(main() or 0)
