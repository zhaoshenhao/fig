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
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class MetricsStore:

    def __init__(self, db_path: str | Path = "data/metrics.db"):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connect(self, row_factory: bool = False):
        """连接上下文管理器，保证异常时也关闭连接。"""
        conn = sqlite3.connect(str(self._db_path))
        if row_factory:
            conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        from src.metrics.dialect import SQLITE
        from src.metrics.migration import migrate
        migrate(conn, SQLITE)
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
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO runs (chat_id, turn_id, workflow_name, query, reply,
                   node_count, duration_ms, status, error_message,
                   prompt_tokens, completion_tokens)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (chat_id, turn_id, workflow_name, query, reply,
                 node_count, duration_ms, status, error_message,
                 prompt_tokens, completion_tokens),
            )
            run_id = cur.lastrowid
            conn.commit()
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
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO node_logs (run_id, chat_id, turn_id, node_name,
                   tool_name, input_data, output_text, duration_ms, status, error_message)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, chat_id, turn_id, node_name,
                 tool_name, input_data, output_text, duration_ms, status, error_message),
            )
            node_log_id = cur.lastrowid
            conn.commit()
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
        with self._connect() as conn:
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
            return tid

    def query_sessions(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        with self._connect(row_factory=True) as conn:
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
            return [dict(r) for r in rows]

    def query_session_turns(
        self,
        chat_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        with self._connect(row_factory=True) as conn:
            rows = conn.execute(
                """SELECT id AS run_id, turn_id, workflow_name, query, reply,
                          node_count, duration_ms, status, error_message,
                          prompt_tokens, completion_tokens, created_at
                   FROM runs
                   WHERE chat_id = ?
                   ORDER BY turn_id ASC
                   LIMIT ? OFFSET ?""",
                (chat_id, limit, offset),
            ).fetchall()
            return [dict(r) for r in rows]

    def query_turn_nodes(
        self,
        run_id: int,
    ) -> list[dict[str, Any]]:
        with self._connect(row_factory=True) as conn:
            rows = conn.execute(
                """SELECT id AS node_log_id, node_name, tool_name,
                          input_data, output_text, duration_ms, status,
                          error_message, created_at
                   FROM node_logs
                   WHERE run_id = ?
                   ORDER BY id ASC""",
                (run_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def query_node_tools(
        self,
        node_log_id: int,
    ) -> list[dict[str, Any]]:
        with self._connect(row_factory=True) as conn:
            rows = conn.execute(
                """SELECT id AS tool_log_id, tool_name, input_params,
                          output_result, duration_ms, status, error_message, created_at
                   FROM tool_logs
                   WHERE node_log_id = ?
                   ORDER BY id ASC""",
                (node_log_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def insert_feedback(
        self,
        chat_id: str,
        turn_id: int,
        rating: str,
        comment: str | None = None,
        correction: str | None = None,
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO feedback (chat_id, turn_id, rating, comment, correction)
                   VALUES (?, ?, ?, ?, ?)""",
                (chat_id, turn_id, rating, comment, correction),
            )
            fid = cur.lastrowid
            conn.commit()
            return fid

    def query_feedback(
        self,
        chat_id: str,
        turn_id: int | None = None,
    ) -> list[dict[str, Any]]:
        sql = ("SELECT id, chat_id, turn_id, rating, comment, correction, created_at "
               "FROM feedback WHERE chat_id = ?")
        params: list[Any] = [chat_id]
        if turn_id is not None:
            sql += " AND turn_id = ?"
            params.append(turn_id)
        sql += " ORDER BY id ASC"
        with self._connect(row_factory=True) as conn:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def insert_rag_retrieval(
        self, run_id: int, chat_id: str, turn_id: int, collection: str,
        score: float = 0.0, source: str = "", chunk_preview: str = "",
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO rag_retrievals (run_id, chat_id, turn_id, collection, "
                "score, source, chunk_preview) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_id, chat_id, turn_id, collection, score, source, chunk_preview[:500]),
            )
            fid = cur.lastrowid
            conn.commit()
            return fid

    def query_rag_for_turn(self, run_id: int) -> list[dict[str, Any]]:
        with self._connect(row_factory=True) as conn:
            rows = conn.execute(
                "SELECT id, collection, score, source, chunk_preview, created_at "
                "FROM rag_retrievals WHERE run_id = ? ORDER BY score DESC",
                (run_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def rag_summary(self, workflow: str | None = None, time_from: str | None = None,
                    time_to: str | None = None) -> dict[str, Any]:
        """RAG 检索质量概览（平均分、命中数、按 collection/source 分布）。

        条件中使用 `runs.created_at` 以保证与 `runs` JOIN 时无歧义。
        """
        conds, params = [], []
        if time_from:
            conds.append("runs.created_at >= ?"); params.append(time_from)
        if time_to:
            conds.append("runs.created_at <= ?"); params.append(time_to)
        if workflow:
            conds.append("runs.workflow_name = ?"); params.append(workflow)
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        with self._connect(row_factory=True) as conn:
            overview = dict(conn.execute(
                f"""SELECT COUNT(*) AS total_chunks, AVG(score) AS avg_score,
                           MIN(score) AS min_score, MAX(score) AS max_score
                    FROM rag_retrievals rr
                    JOIN runs ON runs.id = rr.run_id {where}""",
                params).fetchone() or {})
            by_collection = [dict(r) for r in conn.execute(
                f"""SELECT collection, COUNT(*) AS chunks, AVG(score) AS avg_score,
                            MAX(score) AS max_score
                    FROM rag_retrievals rr
                    JOIN runs ON runs.id = rr.run_id {where}
                    GROUP BY collection ORDER BY chunks DESC""",
                params).fetchall()]
            by_source = [dict(r) for r in conn.execute(
                f"""SELECT source, COUNT(*) AS chunks, AVG(score) AS avg_score
                    FROM rag_retrievals rr
                    JOIN runs ON runs.id = rr.run_id {where}
                    GROUP BY source ORDER BY chunks DESC LIMIT 20""",
                params).fetchall()]
        return {
            "overview": {k: (round(v, 4) if isinstance(v, float) else (v or 0))
                         for k, v in overview.items()},
            "by_collection": [{**r, "avg_score": round(r["avg_score"] or 0, 4)}
                              for r in by_collection],
            "by_source": [{**r, "avg_score": round(r["avg_score"] or 0, 4)}
                          for r in by_source],
        }

    def search_sessions(
        self,
        time_from: str | None = None,
        time_to: str | None = None,
        workflow: str | None = None,
        node: str | None = None,
        tool: str | None = None,
        input_text: str | None = None,
        output_text: str | None = None,
        duration_min: float | None = None,
        duration_max: float | None = None,
        feedback: str | None = None,
        title: str | None = None,
        sort_by: str = "last_at",
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        conditions = []
        params: list[Any] = []

        if time_from:
            conditions.append("r.created_at >= ?")
            params.append(time_from)
        if time_to:
            conditions.append("r.created_at <= ?")
            params.append(time_to)
        if workflow:
            conditions.append("r.workflow_name = ?")  # 精确匹配（下拉选择）
            params.append(workflow)
        if duration_min is not None:
            conditions.append("r.duration_ms >= ?")
            params.append(duration_min)
        if duration_max is not None:
            conditions.append("r.duration_ms <= ?")
            params.append(duration_max)

        if node:
            conditions.append(
                "r.id IN (SELECT DISTINCT run_id FROM node_logs WHERE node_name = ?)"
            )
            params.append(node)
        if tool:
            conditions.append(
                "r.id IN (SELECT DISTINCT run_id FROM node_logs WHERE tool_name = ?)"
            )
            params.append(tool)
        if input_text:
            conditions.append(
                "r.id IN (SELECT DISTINCT run_id FROM node_logs WHERE input_data LIKE ?)"
            )
            params.append(f"%{input_text}%")
        if output_text:
            conditions.append(
                "r.id IN (SELECT DISTINCT run_id FROM node_logs WHERE output_text LIKE ?)"
            )
            params.append(f"%{output_text}%")
        # 用户评价过滤：none=无评价 / up=好评 / down=差评
        if feedback == "none":
            conditions.append("r.chat_id NOT IN (SELECT DISTINCT chat_id FROM feedback)")
        elif feedback in ("up", "down"):
            conditions.append(
                "r.chat_id IN (SELECT DISTINCT chat_id FROM feedback WHERE rating = ?)"
            )
            params.append(feedback)
        if title:
            conditions.append(
                "r.chat_id IN (SELECT chat_id FROM session_meta WHERE title LIKE ?)"
            )
            params.append(f"%{title}%")

        full_where = "WHERE " + " AND ".join(conditions) if conditions else ""

        sort_cols = {
            "last_at": "last_at", "first_at": "first_at",
            "duration_ms": "total_duration_ms", "turn_count": "turn_count",
            "chat_id": "chat_id",
        }
        order_col = sort_cols.get(sort_by, "last_at")
        order_dir = "DESC" if sort_dir == "desc" else "ASC"

        count_sql = f"""
            SELECT COUNT(DISTINCT r.chat_id) AS cnt
            FROM runs r
            {full_where}
        """
        query_sql = f"""
            SELECT r.chat_id,
                   COUNT(DISTINCT r.turn_id) AS turn_count,
                   SUM(r.duration_ms) AS total_duration_ms,
                   MIN(r.created_at) AS first_at,
                   MAX(r.created_at) AS last_at,
                   GROUP_CONCAT(DISTINCT r.workflow_name) AS workflow_names,
                   MAX(sm.title) AS title,
                   MAX(sm.tags) AS tags
            FROM runs r
            LEFT JOIN session_meta sm ON sm.chat_id = r.chat_id
            {full_where}
            GROUP BY r.chat_id
            ORDER BY {order_col} {order_dir}
            LIMIT ? OFFSET ?
        """
        with self._connect(row_factory=True) as conn:
            cnt = conn.execute(count_sql, params).fetchone()["cnt"]
            rows = conn.execute(query_sql, params + [limit, offset]).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["title"] = d.get("title") or ""
            d["tags"] = [t for t in (d.get("tags") or "").split(",") if t]
            result.append(d)
        return result, cnt

    def _load_pricing(self):
        """加载模型定价（config/pricing.yaml），缓存到字典。"""
        import yaml
        from pathlib import Path
        p = Path("config/pricing.yaml")
        if not p.is_file():
            return {}
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        return data.get("models", {}) if data else {}

    def _compute_cost(self, prompt_tokens: int = 0, completion_tokens: int = 0,
                      model: str = "") -> float:
        prompt_tokens = float(prompt_tokens or 0)
        completion_tokens = float(completion_tokens or 0)
        pricing = self._load_pricing()
        m = pricing.get(model) or {}
        # 若指定模型无定价或未指定，取第一个含非零定价的模型
        if not m or (m.get("prompt_per_1k", 0) == 0 and m.get("completion_per_1k", 0) == 0):
            for v in pricing.values():
                if v.get("prompt_per_1k", 0) or v.get("completion_per_1k", 0):
                    m = v
                    break
        ppk = m.get("prompt_per_1k", 0) or 0
        cpk = m.get("completion_per_1k", 0) or 0
        return round((prompt_tokens * ppk + completion_tokens * cpk) / 1000, 6)

    def upsert_session_meta(self, chat_id: str, title: str | None = None,
                            tags: list[str] | None = None) -> None:
        """写入/更新会话元信息（title/tags）到 metrics，持久化便于搜索/显示。"""
        tags_str = ",".join(tags) if tags is not None else None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT chat_id FROM session_meta WHERE chat_id = ?", (chat_id,)
            ).fetchone()
            if row:
                sets, params = [], []
                if title is not None:
                    sets.append("title = ?"); params.append(title)
                if tags_str is not None:
                    sets.append("tags = ?"); params.append(tags_str)
                sets.append("updated_at = datetime('now')")
                params.append(chat_id)
                conn.execute(
                    f"UPDATE session_meta SET {', '.join(sets)} WHERE chat_id = ?", params)
            else:
                conn.execute(
                    "INSERT INTO session_meta (chat_id, title, tags) VALUES (?, ?, ?)",
                    (chat_id, title or "", tags_str or ""))
            conn.commit()

    def get_session_meta(self, chat_id: str) -> dict[str, Any]:
        with self._connect(row_factory=True) as conn:
            row = conn.execute(
                "SELECT chat_id, title, tags, updated_at FROM session_meta WHERE chat_id = ?",
                (chat_id,)).fetchone()
        if not row:
            return {"chat_id": chat_id, "title": "", "tags": []}
        d = dict(row)
        d["tags"] = [t for t in (d.get("tags") or "").split(",") if t]
        return d

    def search_facets(self) -> dict[str, list[str]]:
        """返回可用于下拉筛选的去重值：工作流 / 节点名 / 工具名。"""
        with self._connect() as conn:
            wfs = [r[0] for r in conn.execute(
                "SELECT DISTINCT workflow_name FROM runs ORDER BY workflow_name").fetchall()]
            nodes = [r[0] for r in conn.execute(
                "SELECT DISTINCT node_name FROM node_logs ORDER BY node_name").fetchall()]
            tools = [r[0] for r in conn.execute(
                "SELECT DISTINCT tool_name FROM node_logs "
                "WHERE tool_name IS NOT NULL AND tool_name != '' "
                "ORDER BY tool_name").fetchall()]
        return {"workflows": wfs, "nodes": nodes, "tools": tools}

    @property
    def db_path(self) -> Path:
        return self._db_path

    def aggregate_summary(
        self,
        time_from: str | None = None,
        time_to: str | None = None,
    ) -> dict[str, Any]:
        """仪表盘聚合：总量/错误率/延迟分位/按工作流/按工具/时间趋势。"""
        conds, params = [], []
        if time_from:
            conds.append("created_at >= ?")
            params.append(time_from)
        if time_to:
            conds.append("created_at <= ?")
            params.append(time_to)
        where = ("WHERE " + " AND ".join(conds)) if conds else ""

        with self._connect(row_factory=True) as conn:
            overview = dict(conn.execute(
                f"""SELECT COUNT(*) AS total_runs,
                           COUNT(DISTINCT chat_id) AS total_sessions,
                           SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS error_runs,
                           AVG(duration_ms) AS avg_ms,
                           SUM(prompt_tokens) AS prompt_tokens,
                           SUM(completion_tokens) AS completion_tokens
                    FROM runs {where}""", params).fetchone() or {})

            # 延迟分位（SQLite 无 percentile，取排序后按位置估算）
            durations = [r[0] for r in conn.execute(
                f"SELECT duration_ms FROM runs {where} ORDER BY duration_ms", params
            ).fetchall() if r[0] is not None]

            by_workflow = [dict(r) for r in conn.execute(
                f"""SELECT workflow_name,
                           COUNT(*) AS runs,
                           AVG(duration_ms) AS avg_ms,
                           SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS errors
                    FROM runs {where}
                    GROUP BY workflow_name ORDER BY runs DESC""", params).fetchall()]

            node_where = where.replace("created_at", "created_at")
            # JOIN 查询需限定 r.created_at，避免 runs/node_logs 列名歧义
            join_where = where.replace("created_at", "r.created_at")
            by_tool = [dict(r) for r in conn.execute(
                f"""SELECT tool_name,
                           COUNT(*) AS calls,
                           AVG(duration_ms) AS avg_ms,
                           SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS errors
                    FROM node_logs {node_where}
                    GROUP BY tool_name ORDER BY calls DESC""", params).fetchall()]

            trend = [dict(r) for r in conn.execute(
                f"""SELECT substr(created_at, 1, 13) AS hour,
                           COUNT(*) AS runs,
                           AVG(duration_ms) AS avg_ms,
                           SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS errors
                    FROM runs {where}
                    GROUP BY hour ORDER BY hour DESC LIMIT 48""", params).fetchall()]

            # Per-workflow node stats
            wf_node_rows = conn.execute(
                f"""SELECT r.workflow_name, nl.node_name,
                           COUNT(*) AS calls,
                           AVG(nl.duration_ms) AS avg_ms,
                           SUM(CASE WHEN nl.status='error' THEN 1 ELSE 0 END) AS errors
                    FROM node_logs nl JOIN runs r ON nl.run_id = r.id
                    {join_where}
                    GROUP BY r.workflow_name, nl.node_name
                    ORDER BY calls DESC""", params).fetchall()

            # Per-workflow tool stats
            tool_where = "WHERE nl.tool_name != ''" + (
                " AND " + join_where[6:] if join_where else "")
            wf_tool_rows = conn.execute(
                f"""SELECT r.workflow_name, nl.tool_name,
                           COUNT(*) AS calls,
                           AVG(nl.duration_ms) AS avg_ms,
                           SUM(CASE WHEN nl.status='error' THEN 1 ELSE 0 END) AS errors
                    FROM node_logs nl JOIN runs r ON nl.run_id = r.id
                    {tool_where}
                    GROUP BY r.workflow_name, nl.tool_name
                    ORDER BY calls DESC""", params).fetchall()

            # Per-workflow durations for p95
            wf_dur_rows = conn.execute(
                f"""SELECT workflow_name, duration_ms FROM runs {where}
                    ORDER BY workflow_name, duration_ms""", params).fetchall()

            wf_token_rows = conn.execute(
                f"""SELECT workflow_name, SUM(prompt_tokens) AS pt,
                           SUM(completion_tokens) AS ct
                    FROM runs {where} GROUP BY workflow_name""", params).fetchall()

            wf_session_rows = conn.execute(
                f"""SELECT workflow_name, COUNT(DISTINCT chat_id) AS sessions
                    FROM runs {where} GROUP BY workflow_name""", params).fetchall()

            fb_row = dict(conn.execute(
                f"""SELECT
                        SUM(CASE WHEN rating='up' THEN 1 ELSE 0 END) AS up,
                        SUM(CASE WHEN rating='down' THEN 1 ELSE 0 END) AS down,
                        COUNT(*) AS total,
                        SUM(CASE WHEN (comment IS NOT NULL AND comment != '')
                                   OR (correction IS NOT NULL AND correction != '')
                                 THEN 1 ELSE 0 END) AS with_text
                    FROM feedback {where}""", params).fetchone() or {})

            # Per (workflow, node/tool) durations for p95
            wf_node_dur_rows = conn.execute(
                f"""SELECT r.workflow_name, nl.node_name, nl.duration_ms
                    FROM node_logs nl JOIN runs r ON nl.run_id = r.id
                    {join_where}
                    ORDER BY r.workflow_name, nl.node_name, nl.duration_ms""",
                params).fetchall()
            wf_tool_dur_rows = conn.execute(
                f"""SELECT r.workflow_name, nl.tool_name, nl.duration_ms
                    FROM node_logs nl JOIN runs r ON nl.run_id = r.id
                    {tool_where}
                    ORDER BY r.workflow_name, nl.tool_name, nl.duration_ms""",
                params).fetchall()

            wf_fb_rows = conn.execute(
                f"""SELECT r.workflow_name,
                           SUM(CASE WHEN f.rating='up' THEN 1 ELSE 0 END) AS up,
                           SUM(CASE WHEN f.rating='down' THEN 1 ELSE 0 END) AS down,
                           SUM(CASE WHEN (f.comment IS NOT NULL AND f.comment != '')
                                      OR (f.correction IS NOT NULL AND f.correction != '')
                                    THEN 1 ELSE 0 END) AS with_text
                    FROM feedback f JOIN runs r
                      ON f.chat_id = r.chat_id AND f.turn_id = r.turn_id
                    {join_where}
                    GROUP BY r.workflow_name""", params).fetchall()

        def pct(p: float) -> float:
            if not durations:
                return 0.0
            idx = min(len(durations) - 1, int(len(durations) * p))
            return round(durations[idx], 2)

        # Per-workflow p95
        wf_dur: dict[str, list[float]] = {}
        for r in wf_dur_rows:
            wf_dur.setdefault(r[0], []).append(r[1] or 0)
        wf_p95 = {}
        for wf, durs in wf_dur.items():
            s = sorted(durs)
            idx = min(len(s) - 1, int(len(s) * 0.95))
            wf_p95[wf] = round(s[idx], 2) if s else 0.0

        wf_tokens = {r[0]: (r[1] or 0) + (r[2] or 0) for r in wf_token_rows}
        wf_sessions = {r[0]: int(r[1] or 0) for r in wf_session_rows}
        wf_fb = {r[0]: (r[1] or 0, r[2] or 0, r[3] or 0) for r in wf_fb_rows}
        wf_cost = {}
        for r in wf_token_rows:
            wf_cost[r[0]] = self._compute_cost(
                prompt_tokens=r[1] or 0, completion_tokens=r[2] or 0)

        enriched_wf = []
        for w in by_workflow:
            wn = w["workflow_name"]
            up, down, with_text = wf_fb.get(wn, (0, 0, 0))
            rated = up + down
            runs = w.get("runs", 0) or 0
            enriched_wf.append({
                **dict(w),
                "sessions": wf_sessions.get(wn, 0),
                "error_rate": round(w.get("errors", 0) / w.get("runs", 1), 4),
                "p95_ms": wf_p95.get(wn, 0),
                "tokens": wf_tokens.get(wn, 0),
                "cost_estimated": round(wf_cost.get(wn, 0), 6),
                "feedback_up": up,
                "feedback_down": down,
                "feedback_total": rated,
                "rating_rate": round(rated / runs, 4) if runs else 0.0,
                "satisfaction_rate": round(up / rated, 4) if rated else 0.0,
                "feedback_rate": round(with_text / runs, 4) if runs else 0.0,
            })

        # Build wf_nodes / wf_tools grouped by workflow
        def _p95_map(rows) -> dict:
            grp: dict = {}
            for r in rows:
                grp.setdefault((r[0], r[1]), []).append(r[2] or 0)
            out = {}
            for k, durs in grp.items():
                s = sorted(durs)
                idx = min(len(s) - 1, int(len(s) * 0.95))
                out[k] = round(s[idx], 2) if s else 0.0
            return out

        node_p95 = _p95_map(wf_node_dur_rows)
        tool_p95 = _p95_map(wf_tool_dur_rows)

        wf_nodes: dict[str, list[dict]] = {}
        for r in wf_node_rows:
            wf_nodes.setdefault(r[0], []).append(dict(r))
        for wf in wf_nodes:
            for n in wf_nodes[wf]:
                n["error_rate"] = round(n.get("errors", 0) / n.get("calls", 1), 4)
                n["p95_ms"] = node_p95.get((wf, n["node_name"]), 0.0)

        wf_tools: dict[str, list[dict]] = {}
        for r in wf_tool_rows:
            wf_tools.setdefault(r[0], []).append(dict(r))
        for wf in wf_tools:
            for t in wf_tools[wf]:
                t["error_rate"] = round(t.get("errors", 0) / t.get("calls", 1), 4)
                t["p95_ms"] = tool_p95.get((wf, t["tool_name"]), 0.0)

        def pct(p: float) -> float:
            if not durations:
                return 0.0
            idx = min(len(durations) - 1, int(len(durations) * p))
            return round(durations[idx], 2)

        return {
            "overview": {
                "total_runs": overview.get("total_runs", 0) or 0,
                "total_sessions": overview.get("total_sessions", 0) or 0,
                "error_runs": overview.get("error_runs", 0) or 0,
                "error_rate": round((overview.get("error_runs", 0) or 0)
                                    / (overview.get("total_runs", 0) or 1), 4),
                "avg_ms": round(overview.get("avg_ms") or 0, 2),
                "p50_ms": pct(0.5), "p95_ms": pct(0.95), "p99_ms": pct(0.99),
                "prompt_tokens": overview.get("prompt_tokens", 0) or 0,
                "completion_tokens": overview.get("completion_tokens", 0) or 0,
                "feedback_up": fb_row.get("up", 0) or 0,
                "feedback_down": fb_row.get("down", 0) or 0,
                "feedback_total": fb_row.get("total", 0) or 0,
                "rating_rate": round((fb_row.get("total", 0) or 0)
                                     / (overview.get("total_runs", 0) or 1), 4),
                "satisfaction_rate": round(
                    (fb_row.get("up", 0) or 0) / (fb_row.get("total", 0) or 1), 4),
                "feedback_rate": round((fb_row.get("with_text", 0) or 0)
                                       / (overview.get("total_runs", 0) or 1), 4),
                "cost_estimated": round(self._compute_cost(
                    prompt_tokens=overview.get("prompt_tokens", 0) or 0,
                    completion_tokens=overview.get("completion_tokens", 0) or 0,
                ), 6),
            },
            "by_workflow": enriched_wf,
            "by_tool": by_tool,
            "trend": list(reversed(trend)),
            "wf_nodes": wf_nodes,
            "wf_tools": wf_tools,
        }

    def timeseries(
        self,
        workflow: str,
        time_from: str | None = None,
        time_to: str | None = None,
    ) -> dict[str, Any]:
        """按分钟分桶的时间序列（供图表页折线图使用）。

        返回结构：
            {
              "workflow": ..., "buckets": ["YYYY-MM-DD HH:MM", ...],
              "workflow_series": {requests, avg_ms, p95_ms, active_sessions},
              "nodes": {name: {requests, avg_ms, p95_ms}},
              "tools": {name: {requests, avg_ms, p95_ms}},
            }
        各序列数组与 buckets 对齐（缺失延迟为 null，缺失计数为 0）。
        """
        from collections import defaultdict
        from statistics import mean

        def pct(vals: list[float], p: float) -> float | None:
            if not vals:
                return None
            s = sorted(vals)
            idx = min(len(s) - 1, int(len(s) * p))
            return round(s[idx], 2)

        rconds = ["workflow_name = ?"]
        rparams: list[Any] = [workflow]
        if time_from:
            rconds.append("created_at >= ?")
            rparams.append(time_from)
        if time_to:
            rconds.append("created_at <= ?")
            rparams.append(time_to)
        rwhere = "WHERE " + " AND ".join(rconds)

        nconds = ["r.workflow_name = ?"]
        nparams: list[Any] = [workflow]
        if time_from:
            nconds.append("r.created_at >= ?")
            nparams.append(time_from)
        if time_to:
            nconds.append("r.created_at <= ?")
            nparams.append(time_to)
        nwhere = "WHERE " + " AND ".join(nconds)

        with self._connect(row_factory=True) as conn:
            runs = conn.execute(
                f"SELECT created_at, chat_id, duration_ms FROM runs {rwhere}", rparams
            ).fetchall()
            node_rows = conn.execute(
                f"""SELECT nl.created_at AS created_at, nl.node_name, nl.tool_name,
                           nl.duration_ms
                    FROM node_logs nl JOIN runs r ON nl.run_id = r.id
                    {nwhere}""",
                nparams,
            ).fetchall()
            fb_rows = conn.execute(
                f"""SELECT f.created_at AS created_at, f.rating
                    FROM feedback f JOIN runs r
                      ON f.chat_id = r.chat_id AND f.turn_id = r.turn_id
                    {nwhere}""",
                nparams,
            ).fetchall()

        wf_dur: dict[str, list[float]] = defaultdict(list)
        wf_chats: dict[str, set] = defaultdict(set)
        for r in runs:
            b = (r["created_at"] or "")[:16]
            if not b:
                continue
            wf_dur[b].append(r["duration_ms"] or 0)
            wf_chats[b].add(r["chat_id"])

        buckets = sorted(wf_dur)

        # 反馈按分钟分桶（up/down/满意率），对齐到 runs 的 buckets
        fb_up: dict[str, int] = defaultdict(int)
        fb_down: dict[str, int] = defaultdict(int)
        for fr in fb_rows:
            b = (fr["created_at"] or "")[:16]
            if fr["rating"] == "up":
                fb_up[b] += 1
            elif fr["rating"] == "down":
                fb_down[b] += 1

        def _sat(b: str):
            tot = fb_up[b] + fb_down[b]
            return round(fb_up[b] / tot, 4) if tot else None

        workflow_series = {
            "requests": [len(wf_dur[b]) for b in buckets],
            "avg_ms": [round(mean(wf_dur[b]), 2) if wf_dur[b] else None for b in buckets],
            "p95_ms": [pct(wf_dur[b], 0.95) for b in buckets],
            "active_sessions": [len(wf_chats[b]) for b in buckets],
            "feedback_up": [fb_up[b] for b in buckets],
            "feedback_down": [fb_down[b] for b in buckets],
            "satisfaction": [_sat(b) for b in buckets],
        }

        def group_series(key: str) -> dict[str, dict]:
            store: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
            for nr in node_rows:
                name = nr[key] or "-"
                b = (nr["created_at"] or "")[:16]
                if not b:
                    continue
                store[name][b].append(nr["duration_ms"] or 0)
            out = {}
            for name, bm in store.items():
                out[name] = {
                    "requests": [len(bm.get(b, [])) for b in buckets],
                    "avg_ms": [round(mean(bm[b]), 2) if bm.get(b) else None for b in buckets],
                    "p95_ms": [pct(bm[b], 0.95) if bm.get(b) else None for b in buckets],
                }
            return out

        return {
            "workflow": workflow,
            "buckets": buckets,
            "workflow_series": workflow_series,
            "nodes": group_series("node_name"),
            "tools": group_series("tool_name"),
        }

    def delete_older_than(self, cutoff: str) -> int:
        """删除 created_at < cutoff 的历史记录（数据保留策略）。返回删除的 run 数。"""
        with self._connect() as conn:
            run_ids = [r[0] for r in conn.execute(
                "SELECT id FROM runs WHERE created_at < ?", (cutoff,)).fetchall()]
            if run_ids:
                qmarks = ",".join("?" for _ in run_ids)
                conn.execute(f"DELETE FROM tool_logs WHERE run_id IN ({qmarks})", run_ids)
                conn.execute(f"DELETE FROM node_logs WHERE run_id IN ({qmarks})", run_ids)
                conn.execute(f"DELETE FROM runs WHERE id IN ({qmarks})", run_ids)
                conn.commit()
            return len(run_ids)

    def export_training(
        self,
        workflow: str | None = None,
        status: str = "ok",
        limit: int = 1000,
        only_feedback: str | None = None,
    ) -> list[dict[str, Any]]:
        """导出训练样本：query → reply（附带反馈 rating/correction）。

        Args:
            only_feedback: None=全部；"up"/"down"=仅导出对应反馈的样本。
        """
        conds, params = [], []
        if workflow:
            conds.append("r.workflow_name = ?")
            params.append(workflow)
        if status:
            conds.append("r.status = ?")
            params.append(status)
        conds.append("r.query IS NOT NULL AND r.query != ''")
        conds.append("r.reply IS NOT NULL AND r.reply != ''")
        if only_feedback in ("up", "down"):
            conds.append("f.rating = ?")
            params.append(only_feedback)
        where = "WHERE " + " AND ".join(conds)
        params.append(limit)
        with self._connect(row_factory=True) as conn:
            rows = conn.execute(
                f"""SELECT r.chat_id, r.turn_id, r.workflow_name, r.query, r.reply,
                           r.created_at,
                           f.rating AS feedback_rating,
                           f.comment AS feedback_comment,
                           f.correction AS feedback_correction
                    FROM runs r
                    LEFT JOIN feedback f
                      ON f.chat_id = r.chat_id AND f.turn_id = r.turn_id
                    {where} ORDER BY r.created_at DESC LIMIT ?""",
                params).fetchall()
        return [dict(r) for r in rows]

    def list_feedback(
        self,
        rating: str | None = None,
        workflow: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """列出反馈（JOIN 出 query/reply 上下文），供运营/训练审阅。"""
        conds, params = [], []
        if rating in ("up", "down"):
            conds.append("f.rating = ?")
            params.append(rating)
        if workflow:
            conds.append("r.workflow_name = ?")
            params.append(workflow)
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        params.append(limit)
        with self._connect(row_factory=True) as conn:
            rows = conn.execute(
                f"""SELECT f.id, f.chat_id, f.turn_id, f.rating, f.comment,
                           f.correction, f.created_at,
                           r.workflow_name, r.query, r.reply
                    FROM feedback f
                    LEFT JOIN runs r
                      ON f.chat_id = r.chat_id AND f.turn_id = r.turn_id
                    {where} ORDER BY f.id DESC LIMIT ?""",
                params).fetchall()
        return [dict(r) for r in rows]

    def health_check(self) -> dict[str, Any]:
        """检查指标存储可读写。返回 {ok, engine, detail}。"""
        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.execute("SELECT 1").fetchone()
            # 写测试：临时表 + 回滚，不留下数据
            conn.execute("CREATE TEMP TABLE IF NOT EXISTS _healthcheck (x INTEGER)")
            conn.execute("INSERT INTO _healthcheck VALUES (1)")
            conn.rollback()
            return {"ok": True, "engine": "sqlite", "detail": str(self._db_path)}
        finally:
            conn.close()
