"""Canonical table DDL definitions (dialect-agnostic, single source of truth).

All SQL-driven engines (SQLite / MySQL / PostgreSQL) use these definitions
to generate CREATE TABLE and CREATE INDEX statements.  The dialect parameter
controls autoincrement types, varchar widths, and default timestamp syntax.

Usage:
    from src.metrics.dialect import SQLITE
    from src.metrics.schema import all_table_ddl, all_index_ddl

    for stmt in all_table_ddl(SQLITE):
        conn.execute(stmt)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.metrics.dialect import Dialect

# ---------------------------------------------------------------------------
# Column sets – used by the migration engine for drift detection
# ---------------------------------------------------------------------------

TABLE_COLUMNS: dict[str, list[str]] = {
    "runs": [
        "id",
        "chat_id",
        "turn_id",
        "workflow_name",
        "query",
        "reply",
        "node_count",
        "duration_ms",
        "status",
        "error_message",
        "prompt_tokens",
        "completion_tokens",
        "created_at",
    ],
    "node_logs": [
        "id",
        "run_id",
        "chat_id",
        "turn_id",
        "node_name",
        "tool_name",
        "input_data",
        "output_text",
        "duration_ms",
        "status",
        "error_message",
        "created_at",
    ],
    "tool_logs": [
        "id",
        "node_log_id",
        "run_id",
        "chat_id",
        "turn_id",
        "node_name",
        "tool_name",
        "input_params",
        "output_result",
        "duration_ms",
        "status",
        "error_message",
        "created_at",
    ],
    "feedback": [
        "id",
        "chat_id",
        "turn_id",
        "rating",
        "comment",
        "correction",
        "created_at",
    ],
    "session_meta": [
        "chat_id",
        "title",
        "tags",
        "updated_at",
    ],
    "rag_retrievals": [
        "id",
        "run_id",
        "chat_id",
        "turn_id",
        "collection",
        "score",
        "source",
        "chunk_preview",
        "created_at",
    ],
}

# ---------------------------------------------------------------------------
# DDL generators
# ---------------------------------------------------------------------------


def all_table_ddl(d: Dialect) -> list[str]:
    """Return a list of CREATE TABLE IF NOT EXISTS statements (6 tables)."""
    vc = d.varchar_type
    tx = d.text_type
    ts = d.ts_default
    return [
        f"""CREATE TABLE IF NOT EXISTS runs (
            id            {d.autoincrement},
            chat_id       {tx} NOT NULL,
            turn_id       INTEGER NOT NULL,
            workflow_name {vc} NOT NULL,
            query         {tx},
            reply         {tx},
            node_count    INTEGER DEFAULT 0,
            duration_ms   REAL,
            status        {vc} DEFAULT 'ok',
            error_message {tx},
            prompt_tokens INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            created_at    {vc} DEFAULT {ts}
        )""",
        f"""CREATE TABLE IF NOT EXISTS node_logs (
            id            {d.autoincrement},
            run_id        INTEGER NOT NULL,
            chat_id       {tx} NOT NULL,
            turn_id       INTEGER NOT NULL,
            node_name     {vc} NOT NULL,
            tool_name     {vc} DEFAULT '',
            input_data    {tx},
            output_text   {tx},
            duration_ms   REAL,
            status        {vc} DEFAULT 'ok',
            error_message {tx},
            created_at    {vc} DEFAULT {ts}
        )""",
        f"""CREATE TABLE IF NOT EXISTS tool_logs (
            id             {d.autoincrement},
            node_log_id    INTEGER NOT NULL,
            run_id         INTEGER NOT NULL,
            chat_id        {tx} NOT NULL,
            turn_id        INTEGER NOT NULL,
            node_name      {vc} NOT NULL,
            tool_name      {vc} NOT NULL,
            input_params   {tx},
            output_result  {tx},
            duration_ms    REAL,
            status         {vc} DEFAULT 'ok',
            error_message  {tx},
            created_at     {vc} DEFAULT {ts}
        )""",
        f"""CREATE TABLE IF NOT EXISTS feedback (
            id            {d.autoincrement},
            chat_id       {tx} NOT NULL,
            turn_id       INTEGER NOT NULL,
            rating        {vc} NOT NULL,
            comment       {tx},
            correction    {tx},
            created_at    {vc} DEFAULT {ts}
        )""",
        f"""CREATE TABLE IF NOT EXISTS session_meta (
            chat_id     {vc} PRIMARY KEY,
            title       {tx},
            tags        {tx},
            updated_at  {vc} DEFAULT {ts}
        )""",
        f"""CREATE TABLE IF NOT EXISTS rag_retrievals (
            id            {d.autoincrement},
            run_id        INTEGER NOT NULL,
            chat_id       {tx} NOT NULL,
            turn_id       INTEGER NOT NULL,
            collection    {vc} NOT NULL,
            score         REAL DEFAULT 0,
            source        {vc},
            chunk_preview {tx},
            created_at    {vc} DEFAULT {ts}
        )""",
    ]


def all_index_ddl(d: Dialect) -> list[str]:
    """Return CREATE INDEX SQL strings (9 indexes across all tables).

    All engines except MySQL support ``IF NOT EXISTS`` – for MySQL the
    caller should wrap each statement in try/except to skip duplicates.
    """
    return [
        "CREATE INDEX IF NOT EXISTS idx_runs_chat ON runs(chat_id, turn_id)",
        "CREATE INDEX IF NOT EXISTS idx_runs_workflow ON runs(workflow_name, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_node_logs_run ON node_logs(run_id)",
        "CREATE INDEX IF NOT EXISTS idx_node_logs_chat ON node_logs(chat_id, turn_id)",
        "CREATE INDEX IF NOT EXISTS idx_tool_logs_node ON tool_logs(node_log_id)",
        "CREATE INDEX IF NOT EXISTS idx_tool_logs_run ON tool_logs(run_id)",
        "CREATE INDEX IF NOT EXISTS idx_feedback_chat ON feedback(chat_id, turn_id)",
        "CREATE INDEX IF NOT EXISTS idx_rag_runs ON rag_retrievals(run_id, collection)",
        "CREATE INDEX IF NOT EXISTS idx_rag_chat ON rag_retrievals(chat_id, turn_id)",
    ]
