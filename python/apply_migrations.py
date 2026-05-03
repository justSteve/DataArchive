#!/usr/bin/env python3
"""
Apply database migrations
"""
import sys
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional

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
    """Apply a single migration file.

    Handles idempotent ALTER TABLE ADD COLUMN: if the column already exists
    (e.g. added ad-hoc to production before the migration was formalized),
    the "duplicate column name" error is caught, the migration is recorded
    in schema_migrations, and we return success.
    """
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

    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            # Column already exists (ad-hoc ALTER TABLE applied before this
            # migration was formalized). Record the migration as applied so
            # subsequent runs skip it.
            logger.warning(
                f"Migration {migration_id}: column already exists, "
                f"recording as applied"
            )
            print(f"[OK] Migration {migration_id}: column already exists, "
                  f"recording as applied\n")
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO schema_migrations "
                    "(migration_id, applied_at, description) VALUES (?, ?, ?)",
                    (migration_id, datetime.now().isoformat(),
                     f"Applied (column already existed)")
                )
                conn.commit()
            except sqlite3.Error as rec_err:
                logger.warning(
                    f"Could not record migration {migration_id}: {rec_err}"
                )
            return True
        else:
            logger.error(f"Failed to apply migration {migration_id}: {e}", exc_info=True)
            print(f"[FAILED] Failed to apply migration {migration_id}: {e}\n")
            conn.rollback()
            return False

    except sqlite3.Error as e:
        logger.error(f"Failed to apply migration {migration_id}: {e}", exc_info=True)
        print(f"[FAILED] Failed to apply migration {migration_id}: {e}\n")
        conn.rollback()
        return False


def run_migrations(conn: sqlite3.Connection, migrations_dir: Optional[Path] = None) -> int:
    """Apply all pending migrations to an open connection.

    This is the library-friendly entry point, called by Database._init_schema()
    after the base CREATE TABLE statements have run.

    Args:
        conn: An open sqlite3 connection (caller manages its lifecycle).
        migrations_dir: Path to migrations directory. Defaults to
            <project_root>/migrations/ resolved relative to this file.

    Returns:
        Number of migrations applied (0 if all were already applied or
        no migration files exist).

    Raises:
        RuntimeError: If a migration fails (non-idempotent error).
    """
    if migrations_dir is None:
        # Resolve <repo>/migrations/ relative to this file's location
        migrations_dir = Path(__file__).resolve().parent.parent / "migrations"

    if not migrations_dir.exists():
        logger.debug(f"No migrations directory at {migrations_dir}, skipping")
        return 0

    migration_files = sorted(migrations_dir.glob("*.sql"))
    if not migration_files:
        return 0

    applied = get_applied_migrations(conn)
    applied_count = 0

    for migration_file in migration_files:
        migration_id = migration_file.stem
        if migration_id in applied:
            logger.debug(f"Skipping already applied migration: {migration_id}")
            continue

        if apply_migration(conn, migration_file):
            applied_count += 1
        else:
            raise RuntimeError(
                f"Migration {migration_id} failed; schema may be inconsistent"
            )

    if applied_count:
        logger.info(f"Migrations complete: {applied_count} applied")
    return applied_count


def main():
    db_path = Path("data/archive.db")
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

    conn: Optional[sqlite3.Connection] = None
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
        if conn is not None:
            conn.close()


if __name__ == '__main__':
    main()
