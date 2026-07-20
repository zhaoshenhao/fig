"""跨引擎 SQL Metrics 存储基类 + MySQL / PostgreSQL 适配器。

`SQLMetricsStore` 用 `Dialect` 参数化所有 SQL，实现与 `MetricsStore`(SQLite)
等价的接口。MySQL / PostgreSQL 适配器复用连接池提供的原生连接。

注意：默认引擎仍为 SQLite（见 `MetricsStore`），本模块仅在配置显式选择
mysql / postgresql 时启用。
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from src.metrics.dialect import MYSQL, POSTGRES, Dialect


class SQLMetricsStore:
    """基于任意 DB-API 2.0 连接的 Metrics 存储，SQL 由 Dialect 决定。

    子类需实现 `_connection()`：一个上下文管理器，产出一个 DB-API 连接。
    """

    dialect: Dialect

    def __init__(self, dialect: Dialect):
        self.dialect = dialect
        self._init_db()

    # ---- 子类需实现 ----
    @contextmanager
    def _connection(self):  # pragma: no cover - 抽象
        raise NotImplementedError
        yield  # noqa

    # ---- 内部工具 ----
    def _rows_to_dicts(self, cursor) -> list[dict[str, Any]]:
        cols = [c[0] for c in cursor.description] if cursor.description else []
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def _insert_returning_id(self, conn, sql: str, params: tuple) -> int:
        d = self.dialect
        cur = conn.cursor()
        if d.name == "postgresql":
            cur.execute(d.convert(sql) + " RETURNING id", params)
            new_id = cur.fetchone()[0]
        else:
            cur.execute(d.convert(sql), params)
            new_id = cur.lastrowid
        conn.commit()
        return int(new_id)

    # ---- schema ----
    def _init_db(self) -> None:
        from src.metrics.migration import migrate

        with self._connection() as conn:
            migrate(conn, self.dialect)

    # ---- writes ----
    @staticmethod
    def _now() -> str:
        import datetime as _dt
        return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    def insert_run(self, chat_id, turn_id, workflow_name, query="", reply="",
                   node_count=0, duration_ms=0.0, status="ok", error_message=None,
                   prompt_tokens=0, completion_tokens=0) -> int:
        sql = ("INSERT INTO runs (chat_id, turn_id, workflow_name, query, reply, "
               "node_count, duration_ms, status, error_message, prompt_tokens, "
               "completion_tokens, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)")
        with self._connection() as conn:
            return self._insert_returning_id(conn, sql, (
                chat_id, turn_id, workflow_name, query, reply, node_count,
                duration_ms, status, error_message, prompt_tokens, completion_tokens,
                self._now()))

    def insert_node_log(self, run_id, chat_id, turn_id, node_name, tool_name="",
                        input_data=None, output_text="", duration_ms=0.0,
                        status="ok", error_message=None) -> int:
        sql = ("INSERT INTO node_logs (run_id, chat_id, turn_id, node_name, tool_name, "
               "input_data, output_text, duration_ms, status, error_message, created_at) "
               "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)")
        with self._connection() as conn:
            return self._insert_returning_id(conn, sql, (
                run_id, chat_id, turn_id, node_name, tool_name, input_data,
                output_text, duration_ms, status, error_message, self._now()))

    def insert_tool_log(self, node_log_id, run_id, chat_id, turn_id, node_name,
                        tool_name, input_params=None, output_result=None,
                        duration_ms=0.0, status="ok", error_message=None) -> int:
        sql = ("INSERT INTO tool_logs (node_log_id, run_id, chat_id, turn_id, node_name, "
               "tool_name, input_params, output_result, duration_ms, status, error_message, "
               "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)")
        with self._connection() as conn:
            return self._insert_returning_id(conn, sql, (
                node_log_id, run_id, chat_id, turn_id, node_name, tool_name,
                input_params, output_result, duration_ms, status, error_message,
                self._now()))

    # ---- reads ----
    def _query(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute(self.dialect.convert(sql), params)
            return self._rows_to_dicts(cur)

    def query_session_turns(self, chat_id, limit=50, offset=0):
        return self._query(
            "SELECT id AS run_id, turn_id, workflow_name, query, reply, node_count, "
            "duration_ms, status, error_message, created_at FROM runs "
            "WHERE chat_id = ? ORDER BY turn_id ASC LIMIT ? OFFSET ?",
            (chat_id, limit, offset))

    def query_turn_nodes(self, run_id):
        return self._query(
            "SELECT id AS node_log_id, node_name, tool_name, input_data, output_text, "
            "duration_ms, status, error_message, created_at FROM node_logs "
            "WHERE run_id = ? ORDER BY id ASC", (run_id,))

    def query_node_tools(self, node_log_id):
        return self._query(
            "SELECT id AS tool_log_id, tool_name, input_params, output_result, "
            "duration_ms, status, error_message, created_at FROM tool_logs "
            "WHERE node_log_id = ? ORDER BY id ASC", (node_log_id,))

    def insert_feedback(self, chat_id, turn_id, rating, comment=None, correction=None) -> int:
        sql = ("INSERT INTO feedback (chat_id, turn_id, rating, comment, correction, created_at) "
               "VALUES (?, ?, ?, ?, ?, ?)")
        with self._connection() as conn:
            return self._insert_returning_id(
                conn, sql, (chat_id, turn_id, rating, comment, correction, self._now()))

    def query_feedback(self, chat_id, turn_id=None):
        if turn_id is not None:
            return self._query(
                "SELECT id, chat_id, turn_id, rating, comment, correction, created_at "
                "FROM feedback WHERE chat_id = ? AND turn_id = ? ORDER BY id ASC",
                (chat_id, turn_id))
        return self._query(
            "SELECT id, chat_id, turn_id, rating, comment, correction, created_at "
            "FROM feedback WHERE chat_id = ? ORDER BY id ASC", (chat_id,))

    def list_feedback(self, rating=None, workflow=None, limit=200):
        conds, params = [], []
        if rating in ("up", "down"):
            conds.append("f.rating = ?")
            params.append(rating)
        if workflow:
            conds.append("r.workflow_name = ?")
            params.append(workflow)
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        params.append(limit)
        return self._query(
            "SELECT f.id, f.chat_id, f.turn_id, f.rating, f.comment, f.correction, "
            "f.created_at, r.workflow_name, r.query, r.reply "
            "FROM feedback f LEFT JOIN runs r "
            "ON f.chat_id = r.chat_id AND f.turn_id = r.turn_id "
            f"{where} ORDER BY f.id DESC LIMIT ?", tuple(params))

    # ---- 分析 / 查询（跨引擎，供 API 端点使用） ----
    def search_sessions(self, time_from=None, time_to=None, workflow=None, node=None,
                        tool=None, input_text=None, output_text=None, duration_min=None,
                        duration_max=None, feedback=None, title=None, sort_by="last_at",
                        sort_dir="desc", limit=50, offset=0):
        conds, params = [], []
        if time_from:
            conds.append("r.created_at >= ?"); params.append(time_from)
        if time_to:
            conds.append("r.created_at <= ?"); params.append(time_to)
        if workflow:
            conds.append("r.workflow_name = ?"); params.append(workflow)  # 精确匹配
        if duration_min is not None:
            conds.append("r.duration_ms >= ?"); params.append(duration_min)
        if duration_max is not None:
            conds.append("r.duration_ms <= ?"); params.append(duration_max)
        # 节点名/工具名精确匹配；输入/输出文本子串匹配
        for col, val in (("node_name", node), ("tool_name", tool)):
            if val:
                conds.append(f"r.id IN (SELECT DISTINCT run_id FROM node_logs WHERE {col} = ?)")
                params.append(val)
        for col, val in (("input_data", input_text), ("output_text", output_text)):
            if val:
                conds.append(f"r.id IN (SELECT DISTINCT run_id FROM node_logs WHERE {col} LIKE ?)")
                params.append(f"%{val}%")
        if feedback == "none":
            conds.append("r.chat_id NOT IN (SELECT DISTINCT chat_id FROM feedback)")
        elif feedback in ("up", "down"):
            conds.append("r.chat_id IN (SELECT DISTINCT chat_id FROM feedback WHERE rating = ?)")
            params.append(feedback)
        if title:
            conds.append("r.chat_id IN (SELECT chat_id FROM session_meta WHERE title LIKE ?)")
            params.append(f"%{title}%")
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        sort_cols = {"last_at": "last_at", "first_at": "first_at",
                     "duration_ms": "total_duration_ms", "turn_count": "turn_count",
                     "chat_id": "chat_id"}
        order_col = sort_cols.get(sort_by, "last_at")
        order_dir = "DESC" if sort_dir == "desc" else "ASC"
        gc = self.dialect.group_concat_expr("r.workflow_name")
        count_sql = f"SELECT COUNT(DISTINCT r.chat_id) AS cnt FROM runs r {where}"
        query_sql = (
            f"SELECT r.chat_id, COUNT(DISTINCT r.turn_id) AS turn_count, "
            f"SUM(r.duration_ms) AS total_duration_ms, MIN(r.created_at) AS first_at, "
            f"MAX(r.created_at) AS last_at, {gc} AS workflow_names, "
            f"MAX(sm.title) AS title, MAX(sm.tags) AS tags "
            f"FROM runs r LEFT JOIN session_meta sm ON sm.chat_id = r.chat_id {where} "
            f"GROUP BY r.chat_id ORDER BY {order_col} {order_dir} LIMIT ? OFFSET ?")
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute(self.dialect.convert(count_sql), tuple(params))
            cnt = cur.fetchone()[0]
            cur.execute(self.dialect.convert(query_sql), tuple(params + [limit, offset]))
            rows = self._rows_to_dicts(cur)
        for d in rows:
            d["title"] = d.get("title") or ""
            d["tags"] = [t for t in (d.get("tags") or "").split(",") if t]
        return rows, cnt

    def upsert_session_meta(self, chat_id, title=None, tags=None):
        tags_str = ",".join(tags) if tags is not None else None
        existing = self._query(
            "SELECT chat_id FROM session_meta WHERE chat_id = ?", (chat_id,))
        with self._connection() as conn:
            cur = conn.cursor()
            if existing:
                sets, params = [], []
                if title is not None:
                    sets.append("title = ?"); params.append(title)
                if tags_str is not None:
                    sets.append("tags = ?"); params.append(tags_str)
                params.append(chat_id)
                if sets:
                    cur.execute(self.dialect.convert(
                        f"UPDATE session_meta SET {', '.join(sets)} WHERE chat_id = ?"),
                        tuple(params))
            else:
                cur.execute(self.dialect.convert(
                    "INSERT INTO session_meta (chat_id, title, tags) VALUES (?, ?, ?)"),
                    (chat_id, title or "", tags_str or ""))
            conn.commit()

    def get_session_meta(self, chat_id):
        rows = self._query(
            "SELECT chat_id, title, tags, updated_at FROM session_meta WHERE chat_id = ?",
            (chat_id,))
        if not rows:
            return {"chat_id": chat_id, "title": "", "tags": []}
        d = rows[0]
        d["tags"] = [t for t in (d.get("tags") or "").split(",") if t]
        return d

    def insert_rag_retrieval(self, run_id, chat_id, turn_id, collection,
                              score=0.0, source="", chunk_preview="") -> int:
        sql = ("INSERT INTO rag_retrievals (run_id, chat_id, turn_id, collection, "
               "score, source, chunk_preview, created_at) "
               "VALUES (?, ?, ?, ?, ?, ?, ?, ?)")
        with self._connection() as conn:
            return self._insert_returning_id(conn, sql, (
                run_id, chat_id, turn_id, collection, score, source or "",
                (chunk_preview or "")[:500], self._now()))

    def query_rag_for_turn(self, run_id):
        return self._query(
            "SELECT id, collection, score, source, chunk_preview, created_at "
            "FROM rag_retrievals WHERE run_id = ? ORDER BY score DESC", (run_id,))

    def search_facets(self):
        return {
            "workflows": [r["workflow_name"] for r in self._query(
                "SELECT DISTINCT workflow_name FROM runs ORDER BY workflow_name")],
            "nodes": [r["node_name"] for r in self._query(
                "SELECT DISTINCT node_name FROM node_logs ORDER BY node_name")],
            "tools": [r["tool_name"] for r in self._query(
                "SELECT DISTINCT tool_name FROM node_logs "
                "WHERE tool_name IS NOT NULL AND tool_name != '' ORDER BY tool_name")],
        }

    def delete_older_than(self, cutoff: str) -> int:
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute(self.dialect.convert(
                "SELECT id FROM runs WHERE created_at < ?"), (cutoff,))
            run_ids = [r[0] for r in cur.fetchall()]
            if run_ids:
                marks = ",".join([self.dialect.one()] * len(run_ids))
                for tbl, col in (("tool_logs", "run_id"), ("node_logs", "run_id"),
                                 ("runs", "id")):
                    cur.execute(f"DELETE FROM {tbl} WHERE {col} IN ({marks})", tuple(run_ids))
                conn.commit()
            return len(run_ids)

    def export_training(self, workflow=None, status="ok", limit=1000, only_feedback=None):
        conds, params = [], []
        if workflow:
            conds.append("r.workflow_name = ?"); params.append(workflow)
        if status:
            conds.append("r.status = ?"); params.append(status)
        conds.append("r.query IS NOT NULL AND r.query != ''")
        conds.append("r.reply IS NOT NULL AND r.reply != ''")
        if only_feedback in ("up", "down"):
            conds.append("f.rating = ?"); params.append(only_feedback)
        where = "WHERE " + " AND ".join(conds)
        params.append(limit)
        return self._query(
            "SELECT r.chat_id, r.turn_id, r.workflow_name, r.query, r.reply, r.created_at, "
            "f.rating AS feedback_rating, f.comment AS feedback_comment, "
            "f.correction AS feedback_correction "
            "FROM runs r LEFT JOIN feedback f "
            "ON f.chat_id = r.chat_id AND f.turn_id = r.turn_id "
            f"{where} ORDER BY r.created_at DESC LIMIT ?", tuple(params))

    def _summary_where(self, time_from, time_to):
        conds, params = [], []
        if time_from:
            conds.append("created_at >= ?"); params.append(time_from)
        if time_to:
            conds.append("created_at <= ?"); params.append(time_to)
        return (("WHERE " + " AND ".join(conds)) if conds else ""), params

    def _load_pricing(self):
        import yaml
        from pathlib import Path
        p = Path("config/pricing.yaml")
        if not p.is_file():
            return {}
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        return data.get("models", {}) if data else {}

    def _compute_cost(self, prompt_tokens=0, completion_tokens=0):
        prompt_tokens = float(prompt_tokens or 0)
        completion_tokens = float(completion_tokens or 0)
        pricing = self._load_pricing()
        ppk = cpk = 0.0
        for m in pricing.values() if pricing else {}:
            ppk = m.get("prompt_per_1k", 0) or 0
            cpk = m.get("completion_per_1k", 0) or 0
            if ppk or cpk:
                break
        return round((prompt_tokens * ppk + completion_tokens * cpk) / 1000, 6)

    def aggregate_summary(self, time_from=None, time_to=None):
        from statistics import mean
        where, params = self._summary_where(time_from, time_to)
        jwhere = where.replace("created_at", "r.created_at")

        def pctile(vals, p):
            if not vals:
                return 0.0
            s = sorted(vals)
            return round(s[min(len(s) - 1, int(len(s) * p))], 2)

        ov = (self._query(
            f"SELECT COUNT(*) AS total_runs, COUNT(DISTINCT chat_id) AS total_sessions, "
            f"SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS error_runs, "
            f"AVG(duration_ms) AS avg_ms, SUM(prompt_tokens) AS prompt_tokens, "
            f"SUM(completion_tokens) AS completion_tokens FROM runs {where}", tuple(params))
            or [{}])[0]
        durs = [r["duration_ms"] for r in self._query(
            f"SELECT duration_ms FROM runs {where}", tuple(params)) if r["duration_ms"] is not None]
        by_workflow = self._query(
            f"SELECT workflow_name, COUNT(*) AS runs, AVG(duration_ms) AS avg_ms, "
            f"SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS errors FROM runs {where} "
            f"GROUP BY workflow_name ORDER BY runs DESC", tuple(params))
        by_tool = self._query(
            f"SELECT tool_name, COUNT(*) AS calls, AVG(duration_ms) AS avg_ms, "
            f"SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS errors FROM node_logs {where} "
            f"GROUP BY tool_name ORDER BY calls DESC", tuple(params))
        fb = (self._query(
            "SELECT SUM(CASE WHEN rating='up' THEN 1 ELSE 0 END) AS up, "
            "SUM(CASE WHEN rating='down' THEN 1 ELSE 0 END) AS down, COUNT(*) AS total, "
            "SUM(CASE WHEN (comment IS NOT NULL AND comment != '') "
            "OR (correction IS NOT NULL AND correction != '') THEN 1 ELSE 0 END) AS with_text "
            f"FROM feedback {where}", tuple(params)) or [{}])[0]
        wf_sessions = {r["workflow_name"]: r["sessions"] for r in self._query(
            f"SELECT workflow_name, COUNT(DISTINCT chat_id) AS sessions FROM runs {where} "
            f"GROUP BY workflow_name", tuple(params))}
        wf_cost_data = {r["workflow_name"]: (r["pt"] or 0, r["ct"] or 0) for r in self._query(
            f"SELECT workflow_name, SUM(prompt_tokens) AS pt, SUM(completion_tokens) AS ct "
            f"FROM runs {where} GROUP BY workflow_name", tuple(params))}
        wf_tokens = {k: p + c for k, (p, c) in wf_cost_data.items()}
        wf_p95 = {}
        for r in self._query(f"SELECT workflow_name, duration_ms FROM runs {where}", tuple(params)):
            wf_p95.setdefault(r["workflow_name"], []).append(r["duration_ms"] or 0)
        wf_p95 = {k: pctile(v, 0.95) for k, v in wf_p95.items()}
        wf_fb = {}
        for r in self._query(
            "SELECT r.workflow_name, "
            "SUM(CASE WHEN f.rating='up' THEN 1 ELSE 0 END) AS up, "
            "SUM(CASE WHEN f.rating='down' THEN 1 ELSE 0 END) AS down, "
            "SUM(CASE WHEN (f.comment IS NOT NULL AND f.comment != '') "
            "OR (f.correction IS NOT NULL AND f.correction != '') THEN 1 ELSE 0 END) AS with_text "
            "FROM feedback f JOIN runs r ON f.chat_id=r.chat_id AND f.turn_id=r.turn_id "
            f"{jwhere} GROUP BY r.workflow_name", tuple(params)):
            wf_fb[r["workflow_name"]] = (r["up"] or 0, r["down"] or 0, r["with_text"] or 0)

        def _wf_row(w):
            wn = w["workflow_name"]
            up, down, with_text = wf_fb.get(wn, (0, 0, 0))
            rated = up + down
            runs = w.get("runs", 0) or 0
            return {**w, "sessions": wf_sessions.get(wn, 0),
                    "error_rate": round((w.get("errors") or 0) / (w.get("runs") or 1), 4),
                    "p95_ms": wf_p95.get(wn, 0.0), "tokens": wf_tokens.get(wn, 0),
                    "feedback_up": up, "feedback_down": down, "feedback_total": rated,
                    "rating_rate": round(rated / runs, 4) if runs else 0.0,
                    "satisfaction_rate": round(up / rated, 4) if rated else 0.0,
                    "feedback_rate": round(with_text / runs, 4) if runs else 0.0,
                    "cost_estimated": round(self._compute_cost(
                        *wf_cost_data.get(wn, (0, 0))), 6)}
        enriched_wf = [_wf_row(w) for w in by_workflow]

        def group_detail(name_col):
            rows = self._query(
                f"SELECT r.workflow_name, nl.{name_col} AS name, COUNT(*) AS calls, "
                f"AVG(nl.duration_ms) AS avg_ms, "
                f"SUM(CASE WHEN nl.status='error' THEN 1 ELSE 0 END) AS errors "
                f"FROM node_logs nl JOIN runs r ON nl.run_id = r.id {jwhere} "
                f"GROUP BY r.workflow_name, nl.{name_col}", tuple(params))
            durrows = self._query(
                f"SELECT r.workflow_name, nl.{name_col} AS name, nl.duration_ms AS d "
                f"FROM node_logs nl JOIN runs r ON nl.run_id = r.id {jwhere}", tuple(params))
            p95 = {}
            for r in durrows:
                p95.setdefault((r["workflow_name"], r["name"]), []).append(r["d"] or 0)
            p95 = {k: pctile(v, 0.95) for k, v in p95.items()}
            out = {}
            for r in rows:
                wf = r["workflow_name"]
                key = "node_name" if name_col == "node_name" else "tool_name"
                out.setdefault(wf, []).append({
                    key: r["name"], "calls": r["calls"], "avg_ms": r["avg_ms"],
                    "errors": r["errors"],
                    "error_rate": round((r["errors"] or 0) / (r["calls"] or 1), 4),
                    "p95_ms": p95.get((wf, r["name"]), 0.0)})
            return out

        return {
            "overview": {
                "total_runs": ov.get("total_runs", 0) or 0,
                "total_sessions": ov.get("total_sessions", 0) or 0,
                "error_runs": ov.get("error_runs", 0) or 0,
                "error_rate": round((ov.get("error_runs", 0) or 0) / (ov.get("total_runs", 0) or 1), 4),
                "avg_ms": round(ov.get("avg_ms") or 0, 2),
                "p50_ms": pctile(durs, 0.5), "p95_ms": pctile(durs, 0.95), "p99_ms": pctile(durs, 0.99),
                "prompt_tokens": ov.get("prompt_tokens", 0) or 0,
                "completion_tokens": ov.get("completion_tokens", 0) or 0,
                "feedback_up": fb.get("up", 0) or 0, "feedback_down": fb.get("down", 0) or 0,
                "feedback_total": fb.get("total", 0) or 0,
                "rating_rate": round((fb.get("total", 0) or 0)
                                     / (ov.get("total_runs", 0) or 1), 4),
                "satisfaction_rate": round((fb.get("up", 0) or 0) / (fb.get("total", 0) or 1), 4),
                "feedback_rate": round((fb.get("with_text", 0) or 0)
                                       / (ov.get("total_runs", 0) or 1), 4),
                "cost_estimated": round(self._compute_cost(
                    prompt_tokens=ov.get("prompt_tokens", 0) or 0,
                    completion_tokens=ov.get("completion_tokens", 0) or 0,
                ), 6),
            },
            "by_workflow": enriched_wf, "by_tool": by_tool, "trend": [],
            "wf_nodes": group_detail("node_name"), "wf_tools": group_detail("tool_name"),
        }

    def timeseries(self, workflow, time_from=None, time_to=None):
        from collections import defaultdict
        from statistics import mean

        def pctile(vals, p):
            if not vals:
                return None
            s = sorted(vals)
            return round(s[min(len(s) - 1, int(len(s) * p))], 2)

        rconds = ["workflow_name = ?"]; rparams = [workflow]
        nconds = ["r.workflow_name = ?"]; nparams = [workflow]
        if time_from:
            rconds.append("created_at >= ?"); rparams.append(time_from)
            nconds.append("r.created_at >= ?"); nparams.append(time_from)
        if time_to:
            rconds.append("created_at <= ?"); rparams.append(time_to)
            nconds.append("r.created_at <= ?"); nparams.append(time_to)
        runs = self._query(
            f"SELECT created_at, chat_id, duration_ms FROM runs WHERE {' AND '.join(rconds)}",
            tuple(rparams))
        node_rows = self._query(
            "SELECT nl.created_at AS created_at, nl.node_name, nl.tool_name, nl.duration_ms "
            f"FROM node_logs nl JOIN runs r ON nl.run_id = r.id WHERE {' AND '.join(nconds)}",
            tuple(nparams))
        fb_rows = self._query(
            "SELECT f.created_at AS created_at, f.rating "
            f"FROM feedback f JOIN runs r ON f.chat_id=r.chat_id AND f.turn_id=r.turn_id "
            f"WHERE {' AND '.join(nconds)}", tuple(nparams))

        wf_dur, wf_chats = defaultdict(list), defaultdict(set)
        for r in runs:
            ts = r["created_at"]
            if hasattr(ts, "strftime"):
                ts = ts.strftime("%Y-%m-%d %H:%M")
            else:
                ts = (str(ts or ""))[:16]
            if not ts:
                continue
            wf_dur[ts].append(r["duration_ms"] or 0)
            wf_chats[ts].add(r["chat_id"])
        buckets = sorted(wf_dur)
        fb_up, fb_down = defaultdict(int), defaultdict(int)
        for fr in fb_rows:
            b = (fr["created_at"] or "")[:16]
            if fr["rating"] == "up":
                fb_up[b] += 1
            elif fr["rating"] == "down":
                fb_down[b] += 1

        def _sat(b):
            tot = fb_up[b] + fb_down[b]
            return round(fb_up[b] / tot, 4) if tot else None

        wf_series = {
            "requests": [len(wf_dur[b]) for b in buckets],
            "avg_ms": [round(mean(wf_dur[b]), 2) if wf_dur[b] else None for b in buckets],
            "p95_ms": [pctile(wf_dur[b], 0.95) for b in buckets],
            "active_sessions": [len(wf_chats[b]) for b in buckets],
            "feedback_up": [fb_up[b] for b in buckets],
            "feedback_down": [fb_down[b] for b in buckets],
            "satisfaction": [_sat(b) for b in buckets],
        }

        def grp(key):
            store = defaultdict(lambda: defaultdict(list))
            for nr in node_rows:
                store[nr[key] or "-"][(nr["created_at"] or "")[:16]].append(nr["duration_ms"] or 0)
            out = {}
            for nm, bm in store.items():
                out[nm] = {
                    "requests": [len(bm.get(b, [])) for b in buckets],
                    "avg_ms": [round(mean(bm[b]), 2) if bm.get(b) else None for b in buckets],
                    "p95_ms": [pctile(bm[b], 0.95) if bm.get(b) else None for b in buckets]}
            return out

        return {"workflow": workflow, "buckets": buckets, "workflow_series": wf_series,
                "nodes": grp("node_name"), "tools": grp("tool_name")}

    def health_check(self) -> dict[str, Any]:
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
        return {"ok": True, "engine": self.dialect.name, "detail": self.dialect.name}


class _PoolConnMixin:
    """从连接池借用原生连接的上下文管理器。"""

    def __init__(self, pool, dialect):
        self._pool = pool
        SQLMetricsStore.__init__(self, dialect)

    @contextmanager
    def _connection(self):
        conn = self._pool._acquire()
        try:
            yield conn
        finally:
            self._pool._release(conn)


class MySQLMetricsStore(_PoolConnMixin, SQLMetricsStore):
    def __init__(self, pool):
        super().__init__(pool, MYSQL)


class PostgresMetricsStore(_PoolConnMixin, SQLMetricsStore):
    def __init__(self, pool):
        super().__init__(pool, POSTGRES)
