[中文](database_CN.md)

# Database Configuration & Schema Management

## 1. Overview

The KF system handles two separate database concerns:

1. **Business DB** (`config/db.yaml`): Connection pools used by workflow tools (`db_query` tool)
2. **Metrics DB** (`config/metrics.yaml`): Execution tracing and run log storage

---

## 2. Business Database (Connection Pools)

### Configuration (config/db.yaml)

```yaml
default: mysql_main

pools:
  mysql_main:
    type: mysql
    host: localhost
    port: 3306
    user: root
    password: ${MYSQL_PASSWORD:}
    database: kf
    pool_size: 5

  pg_analytics:
    type: postgresql
    host: localhost
    port: 5432
    user: postgres
    password: ${PG_PASSWORD:}
    database: analytics
    pool_size: 3
```

### Field Reference

| Field | Required | Description |
|-------|----------|-------------|
| `default` | No | Default pool name |
| `pools.{name}.type` | Yes | `mysql` or `postgresql` |
| `pools.{name}.host` | No | Host, default `localhost` |
| `pools.{name}.port` | No | Port (MySQL default 3306, PG default 5432) |
| `pools.{name}.user` | No | Username |
| `pools.{name}.password` | No | Password, supports `${ENV_VAR}` placeholder |
| `pools.{name}.database` | No | Database name |
| `pools.{name}.pool_size` | No | Pool size, default 5 |

### Code Architecture

| Module | Description |
|--------|-------------|
| `src/db/base.py` | `DBConfig`, `DBPoolConfig` dataclasses, `DBPool` ABC |
| `src/db/mysql_pool.py` | `MySQLPool` (pymysql implementation) |
| `src/db/pg_pool.py` | `PgPool` (psycopg2 implementation) |
| `src/db/__init__.py` | `create_pool(name, config)`, `get_db_pool(name)`, `close_all_pools()` |

Pools are created at application startup in `src/api/main.py`.

### Using the db_query Tool

```yaml
tool: db_query
db: mysql_main
query: SELECT * FROM faq WHERE question LIKE %s
params:
  - "%{{query}}%"
limit: 20
```

**Template Variables**:

| Variable | Source |
|----------|--------|
| `{{query}}` | Current user input for this turn |
| `{{chat_id}}` | Session ID |
| `{{_workflow}}` | Workflow name |
| `{{<field>}}` | A `data.<field>` from a predecessor node or a `data_map` field |
| `{{data_map}}` | Entire data_map as a JSON string |

**Return Format**:

```json
{
  "text": "mysql_main\nid, question, answer\n----------------\n1, ...",
  "rows": [
    {"id": 1, "question": "...", "answer": "..."}
  ],
  "db": "mysql_main"
}
```

---

## 3. Metrics Database Schema Management

### Architecture

```
src/metrics/
├── schema.py       # Canonical DDL + column definitions (single source of truth)
├── migration.py    # Migration dataclass + MIGRATIONS list + migrate() engine
├── dialect.py      # SQL dialects (SQLite / MySQL / PostgreSQL)
├── store.py        # MetricsStore (SQLite) → _init_db() calls migrate()
├── sql_store.py    # SQLMetricsStore (MySQL / PG) → _init_db() calls migrate()
└── factory.py      # create_metrics_store() factory
```

### Key Principles

1. **Single source of truth**: All table structures defined in `src/metrics/schema.py`
2. **Versioned migrations**: Changes via `Migration` dataclass with incrementing `version`
3. **Auto-execution**: `_init_db()` → `migrate(conn, dialect)` runs on startup
4. **Non-destructive**: Old tables renamed to `<table>_backup_<YYYYMMDD_HHMMSS>` before migration
5. **Idempotent**: `_schema_version` table tracks applied versions; re-execution is harmless

### How to Add a Migration

**Example**: Add a `cost_estimated` column to the `runs` table.

**Step 1: Update schema.py**

Append `"cost_estimated"` to `TABLE_COLUMNS["runs"]`:

```python
TABLE_COLUMNS: dict[str, list[str]] = {
    "runs": [
        ...
        "created_at",
        "cost_estimated",  # new
    ],
```

Add the column to `all_table_ddl()` runs DDL:

```python
f"""CREATE TABLE IF NOT EXISTS runs (
    ...
    created_at       {vc} DEFAULT {ts},
    cost_estimated   REAL DEFAULT 0
)"""
```

**Step 2: Append Migration**

Add to `MIGRATIONS` list in `src/metrics/migration.py`:

```python
Migration(
    version=2,
    description="Add cost_estimated column to runs",
    table_columns={"runs": TABLE_COLUMNS["runs"]},
    ddl_sql=["ALTER TABLE runs ADD COLUMN cost_estimated REAL DEFAULT 0"],
    index_sql=[],
)
```

**Step 3: Verify**

```bash
python -m pytest tests/test_metrics.py -k "metrics or migration"
```

**Step 4: Deploy** — Auto-executed on API startup; startup aborts if migration fails.

### Migration Rules

| Operation | Migration Action | Example |
|-----------|-----------------|---------|
| New table | `ddl_sql` with `CREATE TABLE` | version 1 |
| New column | `ddl_sql` with `ALTER TABLE ADD COLUMN` | `cost_estimated` |
| Column type change | `table_columns` triggers drift → backup → rebuild | Rare |
| New index | `index_sql` with `CREATE INDEX` | `idx_runs_cost` |
| Drop column | Mark deprecated, clean in next major version | — |

**Forbidden**: Never use `DROP TABLE` or `DELETE` in migrations. Use `_backup_table` for safe data cleanup.

---

## 4. Dependencies

```bash
pip install pymysql              # MySQL
pip install psycopg2-binary      # PostgreSQL
# Or install all production deps at once:
pip install -e .[prod]
```

---

## 5. Connection Pool Lifecycle

- Created at app startup based on `config/db.yaml`
- Connections reused within `pool_size` limit
- `db_query` tool auto-acquires from the pool, returns after query
- All pools closed at application shutdown

---

## 6. Environment Configuration

```bash
# Business databases (matched to ${ENV_VAR} placeholders in config/db.yaml)
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3307
MYSQL_USER=root
MYSQL_PASSWORD=kfpass
MYSQL_DB=kf_metrics

PG_HOST=127.0.0.1
PG_PORT=5433
PG_USER=postgres
PG_PASSWORD=kfpass
PG_DB=kf_analytics

# Metrics database (standalone config, created via factory)
KF_METRICS_DB_HOST=127.0.0.1
KF_METRICS_DB_PORT=3307
KF_METRICS_DB_USER=root
KF_METRICS_DB_PASSWORD=kfpass
KF_METRICS_DB_NAME=kf_metrics
KF_METRICS_DB_TYPE=mysql
```
