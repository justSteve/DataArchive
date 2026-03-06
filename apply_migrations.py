#!/usr/bin/env python3
"""
Apply database migrations
"""
import sys
import sqlite3
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent / 'python'))
from core.logger import get_logger

logger = get_logger(__name__)


def get_applied_migrations(conn: sqlite3.Connection) -> set:
    """Get set of already applied migration IDs"""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT migration_id FROM schema_migrations")
        return {row[0] for row in cursor.fetchall()}
    except sqlite3.OperationalError:
        # Table doesn't exist yet - no migrations applied
        return set()


def apply_migration(conn: sqlite3.Connection, migration_file: Path) -> bool:
    """Apply a single migration file"""
    migration_id = migration_file.stem  # filename without .sql

    try:
        logger.info(f"Applying migration: {migration_id}")
        print(f"Applying migration: {migration_id}")

        with open(migration_file, 'r', encoding='utf-8') as f:
            sql = f.read()

        # Execute the migration
        conn.executescript(sql)
        conn.commit()

        logger.info(f"Successfully applied migration: {migration_id}")
        print(f"[OK] Successfully applied migration: {migration_id}\n")
        return True

    except sqlite3.Error as e:
        logger.error(f"Failed to apply migration {migration_id}: {e}", exc_info=True)
        print(f"[FAILED] Failed to apply migration {migration_id}: {e}\n")
        conn.rollback()
        return False


def main():
    db_path = Path("output/archive.db")
    migrations_dir = Path("migrations")

    if not db_path.exists():
        logger.error(f"Database not found: {db_path}")
        print(f"Error: Database not found: {db_path}")
        print("Please run a scan first to create the database.")
        sys.exit(1)

    if not migrations_dir.exists():
        logger.error(f"Migrations directory not found: {migrations_dir}")
        print(f"Error: Migrations directory not found: {migrations_dir}")
        sys.exit(1)

    try:
        conn = sqlite3.connect(str(db_path))
        logger.info(f"Connected to database: {db_path}")
        print(f"Database: {db_path}\n")

        # Get already applied migrations
        applied = get_applied_migrations(conn)
        logger.info(f"Found {len(applied)} previously applied migrations")
        print(f"Previously applied migrations: {len(applied)}\n")

        # Get all migration files
        migration_files = sorted(migrations_dir.glob("*.sql"))

        if not migration_files:
            logger.warning("No migration files found")
            print("No migration files found.")
            sys.exit(0)

        # Apply migrations in order
        applied_count = 0
        skipped_count = 0

        for migration_file in migration_files:
            migration_id = migration_file.stem

            if migration_id in applied:
                logger.info(f"Skipping already applied migration: {migration_id}")
                print(f"Skipping already applied migration: {migration_id}")
                skipped_count += 1
                continue

            if apply_migration(conn, migration_file):
                applied_count += 1
            else:
                logger.error(f"Migration failed, stopping: {migration_id}")
                print(f"Migration failed, stopping at: {migration_id}")
                sys.exit(1)

        logger.info(f"Migration complete: {applied_count} applied, {skipped_count} skipped")
        print(f"\nMigration complete:")
        print(f"  Applied: {applied_count}")
        print(f"  Skipped: {skipped_count}")
        print(f"  Total: {len(migration_files)}")

    except sqlite3.Error as e:
        logger.error(f"Database error: {e}", exc_info=True)
        print(f"Database error: {e}")
        sys.exit(1)

    finally:
        if 'conn' in locals():
            conn.close()


if __name__ == '__main__':
    main()
