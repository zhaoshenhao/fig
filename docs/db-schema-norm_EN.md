[中文](db-schema-norm.md)

# Database Schema Change Norm

## Core Principles

- **Schema is defined exclusively in `src/metrics/schema.py`** (canonical source of truth)
- **Versioned migrations** live in `src/metrics/migration.py` (`Migration` dataclass + `MIGRATIONS` list)
- Auto-runs `migrate(conn, dialect)` on startup, detects schema drift and backs up old tables
- **Never** commit a migration that drops data without an explicit backup step

---

## Standard Steps to Add a Migration

### 1. Modify Schema Definition

Edit `src/metrics/schema.py` to add/modify column definitions:

```python
# Add new column in all_table_ddl()
def all_table_ddl(dialect):
    ...
    runs_cols = {
        ...
        "new_field": "TEXT",  # new column
    }
```

> Full column definitions: see `COLUMNS` constant.

### 2. Add Migration Entry

Append to the `MIGRATIONS` list in `src/metrics/migration.py`:

```python
Migration(
    version=2,  # current max version + 1
    description="add new_field to runs",
    table_columns={
        "runs": [
            # List ALL expected columns for runs after this migration
            "id", "chat_id", "turn_id", "workflow_name",
            "query", "reply", "node_count", "duration_ms",
            "status", "error_message", "prompt_tokens",
            "completion_tokens", "created_at",
            "new_field",  # new column
        ],
    },
    ddl_sql=[
        "ALTER TABLE runs ADD COLUMN new_field TEXT",
    ],
    index_sql=[
        # Optional: new indexes
        # "CREATE INDEX idx_runs_new_field ON runs(new_field)",
    ],
),
```

### 3. Update Index Definitions

If adding new indexes, add corresponding entries in `all_index_ddl()` in `src/metrics/schema.py`.

### 4. Verify

```bash
# Fresh database
rm -f data/metrics.db
pytest tests/unit/test_metrics.py -v

# Upgrade from previous version (keep old DB file, restart app)
python -m uvicorn src.api.main:app

# Check migration log
grep "migration" logs/app.log
```

### 5. Check Backup

If migration detects schema drift (actual columns ≠ expected), the old table is auto-renamed to `<table>_backup_<YYYYMMDD_HHMMSS>`. Verify backup is correct, then manually drop it.

---

## Migration Data Structure

```python
@dataclass
class Migration:
    version: int                            # Incrementing version number
    description: str                        # Human-readable description
    table_columns: dict[str, list[str]]     # Expected column set for affected tables
    ddl_sql: list[str]                      # DDL statements to execute
    index_sql: list[str]                    # Index creation statements
```

---

## Rules

| Rule | Description |
|------|-------------|
| Version increments | Each Migration `version` must strictly increase |
| Immutable | Migrations are append-only; never modify existing entries |
| Idempotent | `_schema_version` table ensures executed migrations are skipped |
| No data loss | Never use `DROP TABLE`; always backup before altering |
| Test coverage | Every migration must have a corresponding unit test |

---

## Related Files

| File | Purpose |
|------|---------|
| `src/metrics/schema.py` | Authoritative schema definition (DDL + indexes + column lists) |
| `src/metrics/migration.py` | Migration engine + MIGRATIONS list |
| `src/metrics/dialect.py` | SQL dialect abstraction (SQLite / MySQL / PostgreSQL) |
| `src/metrics/store.py` | SQLite MetricsStore, calls `_init_db()` |
| `src/metrics/sql_store.py` | MySQL / PG MetricsStore, calls `_init_db()` |
