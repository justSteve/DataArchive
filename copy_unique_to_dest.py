"""
Copy files from source to destination, skipping duplicates based on hash.

Usage:
    python copy_unique_to_dest.py <source_path> <dest_path> [--dry-run]

Example:
    python copy_unique_to_dest.py D:\ Z:\wTera --dry-run
    python copy_unique_to_dest.py D:\ Z:\wTera
"""

import os
import sys
import hashlib
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "output" / "archive.db"

def compute_hash(file_path, chunk_size=8192):
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            while chunk := f.read(chunk_size):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception as e:
        print(f"Error hashing {file_path}: {e}")
        return None

def hash_exists_in_db(hash_value, conn):
    """Check if hash exists in database."""
    cursor = conn.cursor()
    cursor.execute("SELECT file_path FROM files WHERE hash = ?", (hash_value,))
    return cursor.fetchone() is not None

def get_all_files(source_path):
    """Recursively get all files from source path."""
    files = []
    for root, _, filenames in os.walk(source_path):
        for filename in filenames:
            file_path = os.path.join(root, filename)
            try:
                # Skip if we can't get file stats
                size = os.path.getsize(file_path)
                files.append((file_path, size))
            except Exception as e:
                print(f"Warning: Could not access {file_path}: {e}")
    return files

def copy_unique_files(source_path, dest_path, dry_run=False):
    """Copy files from source to dest, skipping duplicates based on hash."""

    # Connect to database
    if not DB_PATH.exists():
        print(f"Warning: Database not found at {DB_PATH}")
        print("Will copy all files without deduplication.")
        use_db = False
        conn = None
    else:
        conn = sqlite3.connect(DB_PATH)
        use_db = True

    # Get all files from source
    print(f"Scanning {source_path}...")
    files = get_all_files(source_path)
    total_files = len(files)
    print(f"Found {total_files} files")

    # Track statistics
    copied = 0
    skipped_hash = 0
    skipped_exists = 0
    errors = 0
    total_size_copied = 0

    # Process each file
    for idx, (file_path, size) in enumerate(files, 1):
        try:
            # Get relative path for destination
            rel_path = os.path.relpath(file_path, source_path)
            dest_file_path = os.path.join(dest_path, rel_path)

            # Check if file already exists at destination
            if os.path.exists(dest_file_path):
                print(f"[{idx}/{total_files}] SKIP (exists): {rel_path}")
                skipped_exists += 1
                continue

            # Compute hash
            print(f"[{idx}/{total_files}] Hashing: {rel_path}")
            file_hash = compute_hash(file_path)

            if file_hash is None:
                print(f"[{idx}/{total_files}] ERROR: Could not hash {rel_path}")
                errors += 1
                continue

            # Check if hash exists in database
            if use_db and hash_exists_in_db(file_hash, conn):
                print(f"[{idx}/{total_files}] SKIP (duplicate): {rel_path} (hash: {file_hash[:8]}...)")
                skipped_hash += 1
                continue

            # Copy file
            if dry_run:
                print(f"[{idx}/{total_files}] WOULD COPY: {rel_path} ({size:,} bytes)")
                copied += 1
                total_size_copied += size
            else:
                # Create destination directory if needed
                os.makedirs(os.path.dirname(dest_file_path), exist_ok=True)

                print(f"[{idx}/{total_files}] COPYING: {rel_path} ({size:,} bytes)")
                shutil.copy2(file_path, dest_file_path)
                copied += 1
                total_size_copied += size

                # Add to database
                if use_db:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT OR IGNORE INTO files (file_path, size, hash, last_seen)
                        VALUES (?, ?, ?, ?)
                    """, (dest_file_path, size, file_hash, datetime.now().isoformat()))
                    conn.commit()

        except Exception as e:
            print(f"[{idx}/{total_files}] ERROR: {file_path}: {e}")
            errors += 1

    # Close database
    if conn:
        conn.close()

    # Print summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Total files:           {total_files:,}")
    print(f"Copied:                {copied:,} ({total_size_copied:,} bytes)")
    print(f"Skipped (exists):      {skipped_exists:,}")
    print(f"Skipped (duplicate):   {skipped_hash:,}")
    print(f"Errors:                {errors:,}")

    if dry_run:
        print("\n*** DRY RUN - No files were actually copied ***")

def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    source_path = sys.argv[1]
    dest_path = sys.argv[2]
    dry_run = "--dry-run" in sys.argv

    if not os.path.exists(source_path):
        print(f"Error: Source path does not exist: {source_path}")
        sys.exit(1)

    if not os.path.exists(dest_path):
        print(f"Error: Destination path does not exist: {dest_path}")
        print(f"Create it first with: mkdir {dest_path}")
        sys.exit(1)

    print(f"Source:      {source_path}")
    print(f"Destination: {dest_path}")
    print(f"Dry run:     {dry_run}")
    print()

    copy_unique_files(source_path, dest_path, dry_run)

if __name__ == "__main__":
    main()
