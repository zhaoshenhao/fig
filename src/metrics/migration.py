"""Versioned database migration system.

All schema DDL changes go through ``Migration`` objects stored in the
``MIGRATIONS`` list below.  On start-up, ``migrate(conn, dialect)``
applies any pending migrations in order:

1. Reads the current version from ``_schema_version``.
2. For each pending migration:
   - Compares actual column names of affected tables against the expected
     set.  If they differ the old table is **renamed** to
     ``<table>_backup_<YYYYMMDD_HHMMSS>`` before the new DDL runs.
3. Executes the DDL and index SQL.
4. Records the migration version in ``_schema_version``.

The caller (``MetricsStore`` / ``SQLMetricsStore._init_db``) is responsible
for providing a DB-API 2.0 connection object (``sqlite3`` / ``pymysql`` /
``psycopg2``).  The migration engine always uses ``conn.cursor()``.

**How to add a new migration** (the *database change norm*):

1. Add / modify columns in ``src/metrics/schema.py`` (the single source
   of truth for the canonical schema).
2. Append a ``Migration`` entry to the ``MIGRATIONS`` list below.
   Increment ``version`` by 1.
3. Provide ``table_columns`` for every table whose columns are expected
   to change – this is used to detect schema drift.
4. Provide ``ddl_sql`` statements (one or more ``ALTER TABLE ...``,
   ``CREATE TABLE ...``, etc.).
5. Provide ``index_sql`` statements for any new / changed indexes.
6. Run the test suite to ensure the migration applies against a fresh
   database and against an existing database from the previous version.

Never commit a migration that drops data without an explicit backup step.
"""

from __future__ import annotations

import time as _time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.metrics.dialect import Dialect

# ---------------------------------------------------------------------------
# Migration data class
# ---------------------------------------------------------------------------


@dataclass
class Migration:
    """A single, ordered schema migration."""

    version: int
    description: str
    # Expected column sets for tables that this migration touches.
    # Maps table_name → list_of_column_names.
    # Used for drift detection: if actual != expected → backup old table.
    table_columns: dict[str, list[str]] = field(default_factory=dict)
    # DDL to execute (CREATE TABLE, ALTER TABLE, etc.)
    ddl_sql: list[str] = field(default_factory=list)
    # Index creation SQL
    index_sql: list[str] = field(default_factory=list)

    def affected_tables(self) -> list[str]:
        """Tables whose schema is changed by this migration."""
        return list(self.table_columns)


# ---------------------------------------------------------------------------
# Registered migrations (ordered by version)
# ---------------------------------------------------------------------------

MIGRATIONS: list[Migration] = [
    Migration(
        version=1,
        description="Initial schema: 6 tables (runs, node_logs, tool_logs, "
        "feedback, session_meta, rag_retrievals) + 9 indexes",
        table_columns={
            "runs": [
                "id", "chat_id", "turn_id", "workflow_name", "query",
                "reply", "node_count", "duration_ms", "status",
                "error_message", "prompt_tokens", "completion_tokens",
                "created_at",
            ],
            "node_logs": [
                "id", "run_id", "chat_id", "turn_id", "node_name",
                "tool_name", "input_data", "output_text", "duration_ms",
                "status", "error_message", "created_at",
            ],
            "tool_logs": [
                "id", "node_log_id", "run_id", "chat_id", "turn_id",
                "node_name", "tool_name", "input_params", "output_result",
                "duration_ms", "status", "error_message", "created_at",
            ],
            "feedback": [
                "id", "chat_id", "turn_id", "rating", "comment",
                "correction", "created_at",
            ],
            "session_meta": [
                "chat_id", "title", "tags", "updated_at",
            ],
            "rag_retrievals": [
                "id", "run_id", "chat_id", "turn_id", "collection",
                "score", "source", "chunk_preview", "created_at",
            ],
        },
        ddl_sql=[],   # emitted programmatically via schema.py
        index_sql=[],  # emitted programmatically via schema.py
    ),
]

_CURRENT_VERSION = MIGRATIONS[-1].version if MIGRATIONS else 0

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _version_table_sql(d: Dialect) -> str:
    """CREATE TABLE IF NOT EXISTS for _schema_version."""
    vc = d.varchar_type
    return f"""CREATE TABLE IF NOT EXISTS _schema_version (
        version     INTEGER PRIMARY KEY,
        applied_at  {vc},
        description {d.text_type}
    )"""


def _get_current_version(conn: Any, d: Dialect) -> int:
    """Read the highest applied migration version."""
    cur = conn.cursor()
    _ensure_version_table(cur, conn, d)
    cur.execute("SELECT MAX(version) FROM _schema_version")
    row = cur.fetchone()
    return row[0] if row[0] is not None else 0


def _ensure_version_table(cur: Any, conn: Any, d: Dialect):
    cur.execute(_version_table_sql(d))
    conn.commit()


def _get_actual_columns(cur: Any, conn: Any, d: Dialect, table: str) -> set[str]:
    """Return the set of column names currently present in *table*.

    Returns an empty set if the table does not exist.
    """
    if d.name == "sqlite":
        cur.execute(f"PRAGMA table_info({table})")
        rows = cur.fetchall()
        return {r[1] for r in rows}
    elif d.name == "mysql":
        cur.execute(f"SHOW COLUMNS FROM `{table}`")
        rows = cur.fetchall()
        if not rows and cur.description is None:
            return set()
        return {r[0] for r in rows}
    elif d.name == "postgresql":
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = %s",
            (table,),
        )
        return {r[0] for r in cur.fetchall()}
    return set()


def _table_exists(cur: Any, d: Dialect, table: str) -> bool:
    """Check whether *table* exists in the database."""
    if d.name == "sqlite":
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        )
        return cur.fetchone() is not None
    elif d.name == "mysql":
        cur.execute(f"SHOW TABLES LIKE '{table}'")
        return cur.fetchone() is not None
    elif d.name == "postgresql":
        cur.execute(
            "SELECT EXISTS (SELECT FROM information_schema.tables "
            "WHERE table_name = %s)",
            (table,),
        )
        return cur.fetchone()[0]
    return False


def _backup_table(cur: Any, conn: Any, table: str) -> str:
    """Rename *table* to ``<table>_backup_<YYYYMMDD_HHMMSS>``.

    Returns the backup table name so the caller can log it.
    """
    suffix = _time.strftime("%Y%m%d_%H%M%S")
    backup = f"{table}_backup_{suffix}"
    cur.execute(f"ALTER TABLE {table} RENAME TO {backup}")
    conn.commit()
    return backup


def _drop_all_known_indexes(cur: Any, conn: Any):
    try:
        for name in (
            "idx_runs_chat",
            "idx_runs_workflow",
            "idx_node_logs_run",
            "idx_node_logs_chat",
            "idx_tool_logs_node",
            "idx_tool_logs_run",
            "idx_feedback_chat",
            "idx_rag_runs",
            "idx_rag_chat",
        ):
            cur.execute(f"DROP INDEX IF EXISTS {name}")
        conn.commit()
    except Exception:
        conn.rollback()


def _record_migration(cur: Any, conn: Any, migration: Migration):
    cur.execute(
        "INSERT INTO _schema_version (version, applied_at, description) "
        "VALUES (?, ?, ?)",
        (migration.version, _time.strftime("%Y-%m-%d %H:%M:%S"),
         migration.description),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def migrate(conn: Any, d: Dialect) -> int:
    """Apply all pending migrations via *conn*.

    *conn* must be a DB-API 2.0 connection (``sqlite3``/``pymysql``/
    ``psycopg2``).  The caller owns the connection lifecycle (commit/close).

    Returns the number of migrations applied (0 if up-to-date).
    """
    from src.metrics.schema import all_index_ddl, all_table_ddl

    cur = conn.cursor()
    current = _get_current_version(conn, d)
    applied = 0

    for m in MIGRATIONS:
        if m.version <= current:
            continue

        backed_up = False
        for table, expected_cols in m.table_columns.items():
            exists = _table_exists(cur, d, table)
            if exists:
                actual = _get_actual_columns(cur, conn, d, table)
                if actual and actual != set(expected_cols):
                    _backup_table(cur, conn, table)
                    backed_up = True
                    from src.logger import get_logger
                    _log = get_logger(__name__)
                    _log.info("migration v%d: backed up table %s", m.version, table)

        if backed_up:
            _drop_all_known_indexes(cur, conn)

        for stmt in all_table_ddl(d):
            cur.execute(stmt)
        conn.commit()

        # Execute per-migration DDL (ALTER, etc.)
        for stmt in m.ddl_sql:
            cur.execute(stmt)
        conn.commit()

        # Create indexes
        if d.name == "mysql":
            for stmt in all_index_ddl(d):
                try:
                    cur.execute(stmt)
                    conn.commit()
                except Exception:
                    conn.rollback()
        else:
            for stmt in all_index_ddl(d):
                cur.execute(stmt)
            conn.commit()

        for stmt in m.index_sql:
            if d.name == "mysql":
                try:
                    cur.execute(stmt)
                    conn.commit()
                except Exception:
                    conn.rollback()
            else:
                cur.execute(stmt)
                conn.commit()

        _record_migration(cur, conn, m)
        applied += 1

    return applied


def current_schema_version() -> int:
    """Return the latest migration version (readable without a DB connection)."""
    return _CURRENT_VERSION
