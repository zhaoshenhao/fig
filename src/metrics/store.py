"""MetricsStore — 基于 SQLite 的完整执行追踪存储。

三层数据结构:
    runs     → 每轮对话 (session × turn)
    node_logs → 该轮中每个节点的执行
    tool_logs → 节点内每个工具的调用

用途:
    - 训练数据采集 (query → reply 全链路)
    - 性能优化依据 (按节点/工具的 P50/P95 延迟)
    - 调试排错 (每个节点和工具的输入/输出)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class MetricsStore:

    def __init__(self, db_path: str | Path = "data/metrics.db"):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("PRAGMA foreign_keys = ON")

        # 检测旧 schema 并迁移
        existing = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='node_logs'"
        ).fetchone()
        if existing:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(node_logs)").fetchall()]
            if "run_id" not in cols:
                conn.executescript("""
                    DROP TABLE IF EXISTS tool_logs;
                    DROP TABLE IF EXISTS node_logs;
                    DROP TABLE IF EXISTS runs;
                """)

        conn.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id       TEXT    NOT NULL,
                turn_id       INTEGER NOT NULL,
                workflow_name TEXT    NOT NULL,
                query         TEXT,
                reply         TEXT,
                node_count    INTEGER DEFAULT 0,
                duration_ms   REAL,
                status        TEXT    DEFAULT 'ok',
                error_message TEXT,
                created_at    TEXT    DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS node_logs (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id        INTEGER NOT NULL,
                chat_id       TEXT    NOT NULL,
                turn_id       INTEGER NOT NULL,
                node_name     TEXT    NOT NULL,
                tool_name     TEXT    DEFAULT '',
                input_data    TEXT,
                output_text   TEXT,
                duration_ms   REAL,
                status        TEXT    DEFAULT 'ok',
                error_message TEXT,
                created_at    TEXT    DEFAULT (datetime('now')),
                FOREIGN KEY (run_id) REFERENCES runs(id)
            );

            CREATE TABLE IF NOT EXISTS tool_logs (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                node_log_id    INTEGER NOT NULL,
                run_id         INTEGER NOT NULL,
                chat_id        TEXT    NOT NULL,
                turn_id        INTEGER NOT NULL,
                node_name      TEXT    NOT NULL,
                tool_name      TEXT    NOT NULL,
                input_params   TEXT,
                output_result  TEXT,
                duration_ms    REAL,
                status         TEXT    DEFAULT 'ok',
                error_message  TEXT,
                created_at     TEXT    DEFAULT (datetime('now')),
                FOREIGN KEY (node_log_id) REFERENCES node_logs(id),
                FOREIGN KEY (run_id) REFERENCES runs(id)
            );

            CREATE INDEX IF NOT EXISTS idx_runs_chat ON runs(chat_id, turn_id);
            CREATE INDEX IF NOT EXISTS idx_runs_workflow ON runs(workflow_name, created_at);
            CREATE INDEX IF NOT EXISTS idx_node_logs_run ON node_logs(run_id);
            CREATE INDEX IF NOT EXISTS idx_node_logs_chat ON node_logs(chat_id, turn_id);
            CREATE INDEX IF NOT EXISTS idx_tool_logs_node ON tool_logs(node_log_id);
            CREATE INDEX IF NOT EXISTS idx_tool_logs_run ON tool_logs(run_id);
        """)
        conn.commit()
        conn.close()

    def insert_run(
        self,
        chat_id: str,
        turn_id: int,
        workflow_name: str,
        query: str = "",
        reply: str = "",
        node_count: int = 0,
        duration_ms: float = 0.0,
        status: str = "ok",
        error_message: str | None = None,
    ) -> int:
        conn = sqlite3.connect(str(self._db_path))
        cur = conn.execute(
            """INSERT INTO runs (chat_id, turn_id, workflow_name, query, reply,
               node_count, duration_ms, status, error_message)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (chat_id, turn_id, workflow_name, query, reply,
             node_count, duration_ms, status, error_message),
        )
        run_id = cur.lastrowid
        conn.commit()
        conn.close()
        return run_id

    def insert_node_log(
        self,
        run_id: int,
        chat_id: str,
        turn_id: int,
        node_name: str,
        tool_name: str = "",
        input_data: str | None = None,
        output_text: str = "",
        duration_ms: float = 0.0,
        status: str = "ok",
        error_message: str | None = None,
    ) -> int:
        conn = sqlite3.connect(str(self._db_path))
        cur = conn.execute(
            """INSERT INTO node_logs (run_id, chat_id, turn_id, node_name,
               tool_name, input_data, output_text, duration_ms, status, error_message)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, chat_id, turn_id, node_name,
             tool_name, input_data, output_text, duration_ms, status, error_message),
        )
        node_log_id = cur.lastrowid
        conn.commit()
        conn.close()
        return node_log_id

    def insert_tool_log(
        self,
        node_log_id: int,
        run_id: int,
        chat_id: str,
        turn_id: int,
        node_name: str,
        tool_name: str,
        input_params: str | None = None,
        output_result: str | None = None,
        duration_ms: float = 0.0,
        status: str = "ok",
        error_message: str | None = None,
    ) -> int:
        conn = sqlite3.connect(str(self._db_path))
        cur = conn.execute(
            """INSERT INTO tool_logs (node_log_id, run_id, chat_id, turn_id,
               node_name, tool_name, input_params, output_result, duration_ms,
               status, error_message)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (node_log_id, run_id, chat_id, turn_id, node_name,
             tool_name, input_params, output_result, duration_ms,
             status, error_message),
        )
        tid = cur.lastrowid
        conn.commit()
        conn.close()
        return tid

    def query_sessions(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT chat_id,
                      COUNT(DISTINCT turn_id) AS turn_count,
                      SUM(duration_ms) AS total_duration_ms,
                      MIN(created_at) AS first_at,
                      MAX(created_at) AS last_at
               FROM runs
               GROUP BY chat_id
               ORDER BY last_at DESC
               LIMIT ? OFFSET ?""",
            (limit, offset),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def query_session_turns(
        self,
        chat_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT id AS run_id, turn_id, workflow_name, query, reply,
                      node_count, duration_ms, status, error_message, created_at
               FROM runs
               WHERE chat_id = ?
               ORDER BY turn_id ASC
               LIMIT ? OFFSET ?""",
            (chat_id, limit, offset),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def query_turn_nodes(
        self,
        run_id: int,
    ) -> list[dict[str, Any]]:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT id AS node_log_id, node_name, tool_name,
                      input_data, output_text, duration_ms, status,
                      error_message, created_at
               FROM node_logs
               WHERE run_id = ?
               ORDER BY id ASC""",
            (run_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def query_node_tools(
        self,
        node_log_id: int,
    ) -> list[dict[str, Any]]:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT id AS tool_log_id, tool_name, input_params,
                      output_result, duration_ms, status, error_message, created_at
               FROM tool_logs
               WHERE node_log_id = ?
               ORDER BY id ASC""",
            (node_log_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @property
    def db_path(self) -> Path:
        return self._db_path
