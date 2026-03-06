# DataArchive Database Migrations

This directory contains SQL migrations for the DataArchive database schema.

## Migration Naming Convention

`NNN_descriptive_name.sql`

- `NNN`: Three-digit sequence number (001, 002, etc.)
- `descriptive_name`: Brief description in snake_case
- `.sql`: SQL file extension

## Applying Migrations

### Manual Application

```bash
sqlite3 output/archive.db < migrations/001_add_error_tracking.sql
```

### Python Application

```python
from pathlib import Path
import sqlite3

def apply_migration(db_path: str, migration_file: Path):
    """Apply a single migration file"""
    with sqlite3.connect(db_path) as conn:
        with open(migration_file) as f:
            conn.executescript(f.read())
        print(f"Applied migration: {migration_file.name}")

# Apply all migrations in order
db_path = "output/archive.db"
migrations_dir = Path("migrations")
for migration_file in sorted(migrations_dir.glob("*.sql")):
    apply_migration(db_path, migration_file)
```

## Migration History

| ID | File | Description | Applied |
|----|------|-------------|---------|
| 001 | `001_add_error_tracking.sql` | Error tracking, task checkpoints, process monitoring | 2026-03-04 |

## Migration Guidelines

1. **Idempotent**: Use `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`
2. **Backwards Compatible**: Don't drop existing tables or columns
3. **Self-Documenting**: Include comments explaining purpose
4. **Atomic**: Each migration should be a complete, self-contained unit
5. **Testable**: Verify migration can be applied to existing database

## Schema Version Tracking

The `schema_migrations` table tracks which migrations have been applied:

```sql
SELECT * FROM schema_migrations ORDER BY applied_at;
```
