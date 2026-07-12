from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

_proj_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_proj_root))


class TestMetricsStore:

    @pytest.fixture
    def db_path(self, tmp_path):
        return str(tmp_path / "test_metrics.db")

    def test_init_creates_tables(self, db_path):
        from src.metrics.store import MetricsStore

        MetricsStore(db_path)
        assert Path(db_path).exists()

        conn = sqlite3.connect(db_path)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = [r[0] for r in tables]
        conn.close()
        for t in ("runs", "node_logs", "tool_logs"):
            assert t in names

    def test_init_creates_indexes(self, db_path):
        from src.metrics.store import MetricsStore

        MetricsStore(db_path)
        conn = sqlite3.connect(db_path)
        indexes = conn.execute(
            "SELECT name, tbl_name FROM sqlite_master WHERE type='index'"
        ).fetchall()
        conn.close()
        index_names = [r[0] for r in indexes]
        assert "idx_runs_chat" in index_names
        assert "idx_runs_workflow" in index_names
        assert "idx_node_logs_run" in index_names
        assert "idx_node_logs_chat" in index_names
        assert "idx_tool_logs_node" in index_names
        assert "idx_tool_logs_run" in index_names

    def test_init_idempotent(self, db_path):
        from src.metrics.store import MetricsStore

        MetricsStore(db_path)
        MetricsStore(db_path)
        assert Path(db_path).exists()

    def test_insert_run_returns_id(self, db_path):
        from src.metrics.store import MetricsStore

        store = MetricsStore(db_path)
        rid = store.insert_run("c1", 0, "w", "query", "reply", 2, 100.0)
        assert rid == 1

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT * FROM runs WHERE id=1").fetchone()
        conn.close()
        assert row[1] == "c1"
        assert row[2] == 0
        assert row[3] == "w"
        assert row[4] == "query"
        assert row[5] == "reply"

    def test_insert_node_log(self, db_path):
        from src.metrics.store import MetricsStore

        store = MetricsStore(db_path)
        rid = store.insert_run("c1", 0, "w")
        nid = store.insert_node_log(rid, "c1", 0, "retrieve", "rag_search",
                                     '{"k":"v"}', "output", 45.2)
        assert nid == 1

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT * FROM node_logs WHERE id=1").fetchone()
        conn.close()
        assert row[4] == "retrieve"
        assert row[5] == "rag_search"
        assert row[8] == 45.2

    def test_insert_tool_log(self, db_path):
        from src.metrics.store import MetricsStore

        store = MetricsStore(db_path)
        rid = store.insert_run("c1", 0, "w")
        nid = store.insert_node_log(rid, "c1", 0, "retrieve", "rag_search")
        tid = store.insert_tool_log(nid, rid, "c1", 0, "retrieve", "rag_search",
                                     '{"p":1}', '{"r":2}', 30.0)
        assert tid == 1

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT * FROM tool_logs WHERE id=1").fetchone()
        conn.close()
        assert row[6] == "rag_search"
        assert row[9] == 30.0

    def test_query_sessions(self, db_path):
        from src.metrics.store import MetricsStore

        store = MetricsStore(db_path)
        store.insert_run("sess_a", 0, "w", duration_ms=100)
        store.insert_run("sess_a", 1, "w", duration_ms=200)
        store.insert_run("sess_b", 0, "w", duration_ms=50)

        sessions = store.query_sessions()
        assert len(sessions) == 2
        assert sessions[0]["chat_id"] in ("sess_a", "sess_b")

    def test_query_session_turns(self, db_path):
        from src.metrics.store import MetricsStore

        store = MetricsStore(db_path)
        store.insert_run("sess_a", 0, "w", query="q0", reply="r0")
        store.insert_run("sess_a", 1, "w", query="q1", reply="r1")

        turns = store.query_session_turns("sess_a")
        assert len(turns) == 2
        assert turns[0]["turn_id"] == 0
        assert turns[0]["query"] == "q0"
        assert turns[1]["turn_id"] == 1

    def test_query_session_turns_not_found(self, db_path):
        from src.metrics.store import MetricsStore

        store = MetricsStore(db_path)
        turns = store.query_session_turns("no_such")
        assert turns == []

    def test_query_turn_nodes(self, db_path):
        from src.metrics.store import MetricsStore

        store = MetricsStore(db_path)
        rid = store.insert_run("c1", 0, "w")
        store.insert_node_log(rid, "c1", 0, "retrieve", "rag_search")
        store.insert_node_log(rid, "c1", 0, "generate", "llm")

        nodes = store.query_turn_nodes(rid)
        assert len(nodes) == 2
        assert nodes[0]["node_name"] == "retrieve"
        assert nodes[1]["node_name"] == "generate"

    def test_query_node_tools(self, db_path):
        from src.metrics.store import MetricsStore

        store = MetricsStore(db_path)
        rid = store.insert_run("c1", 0, "w")
        nid = store.insert_node_log(rid, "c1", 0, "retrieve", "rag_search")
        store.insert_tool_log(nid, rid, "c1", 0, "retrieve", "rag_search",
                               '{"p":1}', '{"r":2}', 30.0)
        store.insert_tool_log(nid, rid, "c1", 0, "retrieve", "rag_search",
                               '{"p":3}', '{"r":4}', 20.0)

        tools = store.query_node_tools(nid)
        assert len(tools) == 2
        assert tools[0]["tool_name"] == "rag_search"
        assert tools[0]["duration_ms"] == 30.0

    def test_db_path_property(self, db_path):
        from src.metrics.store import MetricsStore

        store = MetricsStore(db_path)
        assert store.db_path == Path(db_path)


class TestSearchSessions:

    @pytest.fixture
    def store(self, tmp_path):
        from src.metrics.store import MetricsStore

        s = MetricsStore(str(tmp_path / "search.db"))
        rid_a = s.insert_run("sess_a", 0, "auto_film", query="你好", reply="您好",
                             duration_ms=120.0)
        s.insert_node_log(rid_a, "sess_a", 0, "intent_classify", "llm",
                          '{"query": "你好"}', "product", 60.0)
        s.insert_node_log(rid_a, "sess_a", 0, "search_kb", "rag_search",
                          '{"q": "膜"}', "隔热膜介绍", 40.0)

        rid_b = s.insert_run("sess_b", 0, "customer_service", query="订单查询",
                             reply="已受理", duration_ms=500.0)
        s.insert_node_log(rid_b, "sess_b", 0, "order_handler", "api_call",
                          '{"order": "123"}', "订单状态", 300.0)
        return s

    def test_no_filters_returns_all(self, store):
        rows, total = store.search_sessions()
        assert total == 2
        assert len(rows) == 2

    def test_filter_by_workflow(self, store):
        rows, total = store.search_sessions(workflow="auto_film")
        assert total == 1
        assert rows[0]["chat_id"] == "sess_a"

    def test_filter_by_node_only(self, store):
        rows, total = store.search_sessions(node="intent_classify")
        assert total == 1
        assert rows[0]["chat_id"] == "sess_a"

    def test_filter_by_tool_only(self, store):
        rows, total = store.search_sessions(tool="api_call")
        assert total == 1
        assert rows[0]["chat_id"] == "sess_b"

    def test_filter_by_input_text_only(self, store):
        rows, total = store.search_sessions(input_text="膜")
        assert total == 1
        assert rows[0]["chat_id"] == "sess_a"

    def test_filter_by_output_text_only(self, store):
        rows, total = store.search_sessions(output_text="订单状态")
        assert total == 1
        assert rows[0]["chat_id"] == "sess_b"

    def test_filter_by_duration_range(self, store):
        rows, total = store.search_sessions(duration_min=200.0)
        assert total == 1
        assert rows[0]["chat_id"] == "sess_b"

    def test_combined_workflow_and_tool(self, store):
        rows, total = store.search_sessions(workflow="auto_film", tool="rag_search")
        assert total == 1
        assert rows[0]["chat_id"] == "sess_a"

    def test_combined_node_and_output(self, store):
        rows, total = store.search_sessions(node="search_kb", output_text="隔热膜")
        assert total == 1
        assert rows[0]["chat_id"] == "sess_a"

    def test_all_node_filters_combined(self, store):
        rows, total = store.search_sessions(
            node="intent_classify", tool="llm",
            input_text="你好", output_text="product",
        )
        assert total == 1
        assert rows[0]["chat_id"] == "sess_a"

    def test_filter_no_match(self, store):
        rows, total = store.search_sessions(node="nonexistent")
        assert total == 0
        assert rows == []

    def test_workflow_exact_match(self, store):
        # 精确匹配：部分名不应命中
        assert store.search_sessions(workflow="auto_film")[1] == 1
        assert store.search_sessions(workflow="auto")[1] == 0

    def test_feedback_filter(self, store):
        store.insert_feedback("sess_a", 0, "up", comment="好")
        assert store.search_sessions(feedback="up")[1] == 1
        assert store.search_sessions(feedback="up")[0][0]["chat_id"] == "sess_a"
        assert store.search_sessions(feedback="down")[1] == 0
        # 无评价：sess_b（未加反馈）
        none_rows, none_total = store.search_sessions(feedback="none")
        assert none_total == 1
        assert none_rows[0]["chat_id"] == "sess_b"

    def test_search_facets(self, store):
        f = store.search_facets()
        assert "auto_film" in f["workflows"]
        assert "intent_classify" in f["nodes"]
        assert set(f["tools"]).issubset({"llm", "rag_search", "router", "api_call"}) or f["tools"]
        assert "" not in f["tools"]

    def test_rag_retrieval_roundtrip(self, store):
        rid = store.insert_run("cr", 0, "wf", query="q", reply="a", duration_ms=50.0)
        store.insert_rag_retrieval(rid, "cr", 0, "car_films", score=0.85,
                                   source="KB.md", chunk_preview="隔热膜可以...")
        store.insert_rag_retrieval(rid, "cr", 0, "car_films", score=0.45,
                                   source="KB.md", chunk_preview="另一种膜...")
        rows = store.query_rag_for_turn(rid)
        assert len(rows) == 2 and rows[0]["score"] == 0.85
        summ = store.rag_summary()
        assert summ["overview"]["total_chunks"] == 2
        assert summ["by_collection"][0]["collection"] == "car_films"
        assert 0.64 < summ["overview"]["avg_score"] < 0.66
        # workflow filter
        assert store.rag_summary(workflow="wf")["overview"]["total_chunks"] == 2
        assert store.rag_summary(workflow="no_wf")["overview"]["total_chunks"] == 0

    def test_session_meta_persist_and_search(self, store):
        store.upsert_session_meta("sess_a", title="VIP 咨询", tags=["vip", "film"])
        meta = store.get_session_meta("sess_a")
        assert meta["title"] == "VIP 咨询" and meta["tags"] == ["vip", "film"]
        # search 结果带 title/tags
        rows, _ = store.search_sessions(workflow="auto_film")
        row = next(r for r in rows if r["chat_id"] == "sess_a")
        assert row["title"] == "VIP 咨询" and row["tags"] == ["vip", "film"]
        # 按标题搜索
        assert store.search_sessions(title="VIP")[1] == 1
        assert store.search_sessions(title="不存在")[1] == 0

    def test_session_meta_partial_update_keeps_tags(self, store):
        store.upsert_session_meta("sess_b", title="旧", tags=["a"])
        store.upsert_session_meta("sess_b", title="新")  # 只改标题
        meta = store.get_session_meta("sess_b")
        assert meta["title"] == "新" and meta["tags"] == ["a"]

    def test_session_meta_missing(self, store):
        meta = store.get_session_meta("nobody")
        assert meta["title"] == "" and meta["tags"] == []

    def test_pagination(self, store):
        rows, total = store.search_sessions(limit=1, offset=0)
        assert total == 2
        assert len(rows) == 1
        rows2, _ = store.search_sessions(limit=1, offset=1)
        assert rows2[0]["chat_id"] != rows[0]["chat_id"]

    def test_sort_by_duration(self, store):
        rows, _ = store.search_sessions(sort_by="duration_ms", sort_dir="desc")
        assert rows[0]["chat_id"] == "sess_b"
        rows2, _ = store.search_sessions(sort_by="duration_ms", sort_dir="asc")
        assert rows2[0]["chat_id"] == "sess_a"

    def test_time_range_filter(self, store):
        rows, total = store.search_sessions(time_from="2000-01-01 00:00:00")
        assert total == 2
        rows2, total2 = store.search_sessions(time_to="2000-01-01 00:00:00")
        assert total2 == 0


class TestAggregatesRetentionExport:

    @pytest.fixture
    def store(self, tmp_path):
        from src.metrics.store import MetricsStore

        s = MetricsStore(str(tmp_path / "agg.db"))
        r1 = s.insert_run("s1", 0, "auto_film", query="隔热膜", reply="答复A",
                          duration_ms=120.0, prompt_tokens=10, completion_tokens=20)
        s.insert_node_log(r1, "s1", 0, "search_kb", "rag_search", None, "out", 40.0)
        r2 = s.insert_run("s2", 0, "auto_film", query="车衣", reply="答复B",
                          duration_ms=800.0, status="error", error_message="boom")
        s.insert_node_log(r2, "s2", 0, "gen", "llm", None, "out", 700.0,
                          status="error", error_message="boom")
        return s

    def test_token_columns_persisted(self, store):
        turns = store.query_session_turns("s1")
        assert turns[0]["prompt_tokens"] == 10
        assert turns[0]["completion_tokens"] == 20

    def test_aggregate_summary(self, store):
        summ = store.aggregate_summary()
        ov = summ["overview"]
        assert ov["total_runs"] == 2
        assert ov["error_runs"] == 1
        assert ov["error_rate"] == 0.5
        assert ov["prompt_tokens"] == 10
        assert ov["p95_ms"] >= ov["p50_ms"]
        assert any(w["workflow_name"] == "auto_film" for w in summ["by_workflow"])
        tool_names = [t["tool_name"] for t in summ["by_tool"]]
        assert "rag_search" in tool_names and "llm" in tool_names

    def test_aggregate_summary_feedback_rates(self, store):
        # sess_a turn0 好评+纠错文本；sess_a turn0 只算一条评价
        store.insert_feedback("sess_a", 0, "up", comment="很清楚")
        summ = store.aggregate_summary()
        ov = summ["overview"]
        # 2 runs, 1 rating(up, 带文字)
        assert ov["feedback_total"] == 1
        assert ov["rating_rate"] == 0.5
        assert ov["satisfaction_rate"] == 1.0
        assert ov["feedback_rate"] == 0.5
        # cost 字段存在
        assert "cost_estimated" in ov
        wf = next(w for w in summ["by_workflow"] if w["workflow_name"] == "auto_film")
        assert "cost_estimated" in wf
        for k in ("rating_rate", "satisfaction_rate", "feedback_rate"):
            assert k in wf

    def test_aggregate_summary_per_workflow_detail(self, store):
        summ = store.aggregate_summary()
        wf = next(w for w in summ["by_workflow"] if w["workflow_name"] == "auto_film")
        # 工作流指标：总请求/总会话/错误率/平均耗时/P95/总token
        for k in ("runs", "sessions", "error_rate", "avg_ms", "p95_ms", "tokens"):
            assert k in wf
        assert wf["tokens"] == 30
        # 每工作流反馈（好评率）
        for k in ("feedback_up", "feedback_down", "feedback_total", "satisfaction_rate"):
            assert k in wf
        # 节点/工具明细含 p95 与错误率
        assert "wf_nodes" in summ and "wf_tools" in summ
        nodes = summ["wf_nodes"]["auto_film"]
        assert all("p95_ms" in n and "error_rate" in n and "calls" in n for n in nodes)
        gen = next(n for n in nodes if n["node_name"] == "gen")
        assert gen["error_rate"] == 1.0
        tools = summ["wf_tools"]["auto_film"]
        assert all("p95_ms" in t and "error_rate" in t for t in tools)

    def test_export_training_filters_ok_only(self, store):
        rows = store.export_training(status="ok")
        assert len(rows) == 1
        assert rows[0]["reply"] == "答复A"

    def test_export_training_by_workflow(self, store):
        rows = store.export_training(workflow="auto_film", status="")
        assert len(rows) == 2

    def test_export_training_includes_feedback(self, store):
        # 给 s1 turn0 加反馈，导出应带 feedback_* 字段
        store.insert_feedback("s1", 0, "up", comment="clear")
        rows = store.export_training(status="ok")
        assert "feedback_rating" in rows[0]
        assert "feedback_comment" in rows[0]
        assert "feedback_correction" in rows[0]
        s1 = next(r for r in rows if r["chat_id"] == "s1")
        assert s1["feedback_rating"] == "up"
        assert s1["feedback_comment"] == "clear"

    def test_export_training_only_feedback(self, store):
        store.insert_feedback("s1", 0, "up")
        rows = store.export_training(status="", only_feedback="up")
        assert all(r["feedback_rating"] == "up" for r in rows)
        assert len(rows) == 1

    def test_list_feedback(self, store):
        store.insert_feedback("s1", 0, "up", comment="good")
        store.insert_feedback("s2", 0, "down", correction="fix")
        allfb = store.list_feedback()
        assert len(allfb) == 2
        # JOIN 出 query/reply 上下文
        assert all("query" in f and "workflow_name" in f for f in allfb)
        downs = store.list_feedback(rating="down")
        assert len(downs) == 1 and downs[0]["correction"] == "fix"

    def test_delete_older_than_removes_all(self, store):
        deleted = store.delete_older_than("2999-01-01 00:00:00")
        assert deleted == 2
        assert store.query_session_turns("s1") == []

    def test_delete_older_than_keeps_recent(self, store):
        deleted = store.delete_older_than("2000-01-01 00:00:00")
        assert deleted == 0

    def test_timeseries_structure(self, store):
        ts = store.timeseries("auto_film")
        assert ts["workflow"] == "auto_film"
        assert isinstance(ts["buckets"], list)
        assert len(ts["buckets"]) >= 1
        ws = ts["workflow_series"]
        for key in ("requests", "avg_ms", "p95_ms", "active_sessions",
                    "feedback_up", "feedback_down", "satisfaction"):
            assert key in ws
            assert len(ws[key]) == len(ts["buckets"])
        # 两条 run（s1/s2）→ 请求量与活跃会话
        assert sum(ws["requests"]) == 2
        assert max(ws["active_sessions"]) >= 1
        assert "search_kb" in ts["nodes"]
        assert "gen" in ts["nodes"]
        assert "rag_search" in ts["tools"]
        # 每个序列与 buckets 对齐
        assert len(ts["nodes"]["search_kb"]["p95_ms"]) == len(ts["buckets"])

    def test_timeseries_empty_for_unknown_workflow(self, store):
        ts = store.timeseries("no_such_wf")
        assert ts["buckets"] == []
        assert ts["nodes"] == {}
        assert ts["tools"] == {}


class TestSQLMetricsStoreBase:
    """用 SQLite 后端验证跨引擎 SQLMetricsStore 基类逻辑。"""

    @pytest.fixture
    def store(self, tmp_path):
        import sqlite3
        from contextlib import contextmanager

        from src.metrics.dialect import SQLITE
        from src.metrics.sql_store import SQLMetricsStore

        db = str(tmp_path / "base.db")

        class _SqliteBase(SQLMetricsStore):
            @contextmanager
            def _connection(self):
                conn = sqlite3.connect(db)
                try:
                    yield conn
                finally:
                    conn.close()

        return _SqliteBase(SQLITE)

    def test_insert_and_query_roundtrip(self, store):
        rid = store.insert_run("c1", 0, "wf", query="q", reply="a", duration_ms=5.0)
        assert rid >= 1
        nid = store.insert_node_log(rid, "c1", 0, "n1", "llm", None, "out", 3.0)
        store.insert_tool_log(nid, rid, "c1", 0, "n1", "llm", "{}", "{}", 2.0)

        turns = store.query_session_turns("c1")
        assert turns[0]["workflow_name"] == "wf"
        nodes = store.query_turn_nodes(rid)
        assert nodes[0]["node_name"] == "n1"
        tools = store.query_node_tools(nid)
        assert tools[0]["tool_name"] == "llm"

    def test_health_check(self, store):
        hc = store.health_check()
        assert hc["ok"] is True
        assert hc["engine"] == "sqlite"

    def test_feedback_roundtrip(self, store):
        store.insert_run("c1", 0, "wf", query="q", reply="a")
        fid = store.insert_feedback("c1", 0, "up", comment="good", correction=None)
        assert fid >= 1
        store.insert_feedback("c2", 0, "down", correction="fix")
        one = store.query_feedback("c1", 0)
        assert one[0]["rating"] == "up" and one[0]["comment"] == "good"
        allc1 = store.query_feedback("c1")
        assert len(allc1) == 1
        listed = store.list_feedback()
        assert len(listed) == 2
        downs = store.list_feedback(rating="down")
        assert len(downs) == 1 and downs[0]["correction"] == "fix"

    def test_base_analytics(self, store):
        r1 = store.insert_run("c1", 0, "wf", query="hi", reply="yo",
                              duration_ms=100.0, prompt_tokens=4, completion_tokens=6)
        store.insert_node_log(r1, "c1", 0, "n1", "llm", None, "out", 80.0)
        r2 = store.insert_run("c2", 0, "wf", query="q2", reply="a2",
                              duration_ms=300.0, status="error", error_message="e")
        store.insert_node_log(r2, "c2", 0, "n1", "llm", None, "out", 250.0,
                              status="error", error_message="e")
        store.insert_feedback("c1", 0, "up")

        rows, total = store.search_sessions(workflow="wf")
        assert total == 2 and len(rows) == 2
        assert rows[0]["workflow_names"] == "wf"
        rows2, _ = store.search_sessions(node="n1", tool="llm", sort_by="duration_ms")
        assert len(rows2) == 2

        summ = store.aggregate_summary()
        assert summ["overview"]["total_runs"] == 2
        assert summ["overview"]["feedback_up"] == 1
        assert summ["overview"]["satisfaction_rate"] == 1.0
        assert "wf" in summ["wf_nodes"] and "wf" in summ["wf_tools"]

        ts = store.timeseries("wf")
        assert len(ts["buckets"]) >= 1
        assert "n1" in ts["nodes"] and "llm" in ts["tools"]

        exp = store.export_training(status="")
        assert exp and "feedback_rating" in exp[0]

        assert store.delete_older_than("2999-01-01 00:00:00") == 2

    def test_base_session_meta(self, store):
        store.insert_run("cm", 0, "wf", query="q", reply="a", duration_ms=5.0)
        store.upsert_session_meta("cm", title="标题", tags=["x", "y"])
        assert store.get_session_meta("cm")["title"] == "标题"
        # 更新分支（已存在记录）：只改标题，保留 tags
        store.upsert_session_meta("cm", title="新标题")
        m = store.get_session_meta("cm")
        assert m["title"] == "新标题" and m["tags"] == ["x", "y"]
        assert store.get_session_meta("missing")["title"] == ""
        rows, _ = store.search_sessions(workflow="wf")
        row = next(r for r in rows if r["chat_id"] == "cm")
        assert row["title"] == "新标题" and row["tags"] == ["x", "y"]
        assert store.search_sessions(title="新标题")[1] == 1

    def test_base_search_filters(self, store):
        r = store.insert_run("cf", 0, "wf", query="hello", reply="hi", duration_ms=100.0)
        store.insert_node_log(r, "cf", 0, "n1", "llm", "in-data", "out-data", 80.0)
        store.insert_feedback("cf", 0, "up")
        # 各过滤分支
        assert store.search_sessions(node="n1")[1] == 1
        assert store.search_sessions(tool="llm")[1] == 1
        assert store.search_sessions(input_text="in-data")[1] == 1
        assert store.search_sessions(output_text="out-data")[1] == 1
        assert store.search_sessions(feedback="up")[1] == 1
        assert store.search_sessions(feedback="none")[1] == 0
        assert store.search_sessions(duration_min=1, duration_max=999)[1] == 1
        assert store.search_sessions(time_from="2000-01-01 00:00:00")[1] == 1


class TestMetricsFactory:
    def test_default_is_sqlite(self, tmp_path):
        from src.metrics.factory import create_metrics_store
        from src.metrics.store import MetricsStore

        s = create_metrics_store({"path": str(tmp_path / "f.db")})
        assert isinstance(s, MetricsStore)

    def test_unknown_engine_raises(self, monkeypatch):
        from src.metrics.factory import create_metrics_store

        monkeypatch.setenv("KF_METRICS_ENGINE", "oracle")
        with pytest.raises(ValueError):
            create_metrics_store()


class TestFeedback:
    def test_insert_and_query(self, tmp_path):
        from src.metrics.store import MetricsStore

        s = MetricsStore(str(tmp_path / "fb.db"))
        fid = s.insert_feedback("c1", 0, "up", comment="nice", correction=None)
        assert fid >= 1
        s.insert_feedback("c1", 1, "down", comment="wrong", correction="正确答案")

        all_fb = s.query_feedback("c1")
        assert len(all_fb) == 2
        turn0 = s.query_feedback("c1", 0)
        assert len(turn0) == 1 and turn0[0]["rating"] == "up"
        turn1 = s.query_feedback("c1", 1)
        assert turn1[0]["correction"] == "正确答案"

    def test_query_empty(self, tmp_path):
        from src.metrics.store import MetricsStore

        s = MetricsStore(str(tmp_path / "fb2.db"))
        assert s.query_feedback("nobody") == []


class TestDialect:
    def test_placeholder_conversion(self):
        from src.metrics.dialect import MYSQL, POSTGRES, SQLITE

        sql = "SELECT * FROM t WHERE a = ? AND b = ?"
        assert SQLITE.convert(sql) == sql
        assert MYSQL.convert(sql) == "SELECT * FROM t WHERE a = %s AND b = %s"
        assert POSTGRES.convert(sql).count("%s") == 2

    def test_group_concat_expr(self):
        from src.metrics.dialect import MYSQL, POSTGRES

        assert "GROUP_CONCAT" in MYSQL.group_concat_expr("x")
        assert "string_agg" in POSTGRES.group_concat_expr("x")

    def test_ph_and_one(self):
        from src.metrics.dialect import MYSQL, SQLITE

        assert SQLITE.one() == "?"
        assert MYSQL.one() == "%s"
        assert SQLITE.ph(3) == "?, ?, ?"
        assert MYSQL.ph(2) == "%s, %s"


class TestSchemaMigration:
    def test_old_schema_backed_up_not_dropped(self, tmp_path):
        import sqlite3

        db = str(tmp_path / "old.db")
        # 构造旧 schema：node_logs 无 run_id 列
        conn = sqlite3.connect(db)
        conn.executescript("""
            CREATE TABLE runs (id INTEGER PRIMARY KEY, chat_id TEXT);
            CREATE TABLE node_logs (id INTEGER PRIMARY KEY, chat_id TEXT, node_name TEXT);
            CREATE TABLE tool_logs (id INTEGER PRIMARY KEY);
            INSERT INTO node_logs (chat_id, node_name) VALUES ('old', 'legacy');
        """)
        conn.commit()
        conn.close()

        from src.metrics.store import MetricsStore
        MetricsStore(db)  # 触发迁移

        conn = sqlite3.connect(db)
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        # 新表存在
        assert "runs" in tables and "node_logs" in tables and "tool_logs" in tables
        # 旧数据被备份而非丢弃
        backups = [t for t in tables if t.startswith("node_logs_backup_")]
        assert backups, "旧 node_logs 应被重命名为备份表"
        legacy = conn.execute(
            f"SELECT node_name FROM {backups[0]}").fetchone()
        conn.close()
        assert legacy[0] == "legacy"
        # 新 node_logs 有 run_id 列
        s = MetricsStore(db)
        rid = s.insert_run("c", 0, "wf")
        assert s.insert_node_log(rid, "c", 0, "n", "llm") >= 1


class TestTimeFilters:
    @pytest.fixture
    def store(self, tmp_path):
        from src.metrics.store import MetricsStore

        s = MetricsStore(str(tmp_path / "tf.db"))
        r = s.insert_run("c1", 0, "auto_film", query="q", reply="a", duration_ms=50)
        s.insert_node_log(r, "c1", 0, "n1", "llm", None, "o", 30)
        return s

    def test_aggregate_summary_time_filters(self, store):
        # 未来窗口 → 无数据
        summ = store.aggregate_summary(time_from="2999-01-01 00:00:00")
        assert summ["overview"]["total_runs"] == 0
        # 全历史窗口 → 有数据
        summ2 = store.aggregate_summary(time_from="2000-01-01 00:00:00",
                                        time_to="2999-01-01 00:00:00")
        assert summ2["overview"]["total_runs"] == 1

    def test_timeseries_time_filters(self, store):
        ts = store.timeseries("auto_film", time_from="2000-01-01 00:00:00",
                              time_to="2999-01-01 00:00:00")
        assert sum(ts["workflow_series"]["requests"]) == 1
        ts2 = store.timeseries("auto_film", time_from="2999-01-01 00:00:00")
        assert ts2["buckets"] == []


class TestMetricsFactoryEngines:
    def test_factory_mysql_branch(self, mocker):
        from src.metrics import factory

        fake_pool = mocker.MagicMock()
        mocker.patch("src.db.get_db_pool", return_value=fake_pool)
        mysql_cls = mocker.patch("src.metrics.sql_store.MySQLMetricsStore")
        store = factory.create_metrics_store({"engine": "mysql", "pool": "metrics"})
        mysql_cls.assert_called_once_with(fake_pool)
        assert store is mysql_cls.return_value

    def test_factory_postgres_branch(self, mocker):
        from src.metrics import factory

        fake_pool = mocker.MagicMock()
        mocker.patch("src.db.get_db_pool", return_value=fake_pool)
        pg_cls = mocker.patch("src.metrics.sql_store.PostgresMetricsStore")
        store = factory.create_metrics_store({"engine": "postgresql", "pool": "m"})
        pg_cls.assert_called_once_with(fake_pool)
        assert store is pg_cls.return_value

    def test_factory_env_override(self, tmp_path, monkeypatch):
        from src.metrics.factory import create_metrics_store
        from src.metrics.store import MetricsStore

        monkeypatch.setenv("KF_METRICS_ENGINE", "sqlite")
        monkeypatch.setenv("KF_METRICS_DB_PATH", str(tmp_path / "env.db"))
        s = create_metrics_store({"engine": "mysql"})  # env 覆盖 → sqlite
        assert isinstance(s, MetricsStore)


class TestDAGMetricsIntegration:

    def test_run_collects_run_and_nodes(self, tmp_path, mocker):
        db_path = str(tmp_path / "integration_metrics.db")
        from src.metrics.store import MetricsStore
        metrics = MetricsStore(db_path)

        from src.engine import DAGEngine, ToolRegistry
        from src.session.data import SessionData

        registry = ToolRegistry()
        registry.register("llm", lambda c, s: {"text": "mock answer"})
        registry.register("rag_search", lambda c, s: {"text": "mock knowledge"})

        app_config = mocker.MagicMock()
        app_config.session = None
        app_config.workflows = {
            "test_wf": {
                "_product": "default",
                "return_mode": "full",
                "nodes": [
                    {"name": "retrieve", "next_type": "one", "next": "generate"},
                    {"name": "generate", "next_type": "one", "next": ""},
                ],
            }
        }
        app_config.node_config = lambda key: (
            {"tool": "rag_search", "collections": ["default"]}
            if "retrieve" in key
            else {"tool": "llm", "system_prompt": "hello"}
        )

        engine = DAGEngine(tools=registry, app_config=app_config, metrics_store=metrics)
        session = SessionData()
        engine.run("test_wf", {"query": "hi"}, session)

        conn = sqlite3.connect(db_path)
        runs = conn.execute("SELECT * FROM runs").fetchall()
        assert len(runs) == 1
        assert runs[0][3] == "test_wf"

        nodes = conn.execute("SELECT node_name, tool_name FROM node_logs ORDER BY id").fetchall()
        node_names = [r[0] for r in nodes]
        assert "retrieve" in node_names
        assert "generate" in node_names

        tools = conn.execute("SELECT tool_name FROM tool_logs").fetchall()
        assert len(tools) >= 2
        conn.close()

    def test_run_increments_turn_id(self):
        from src.session.data import SessionData

        session = SessionData()
        assert session.turn_id == 0
        session.add_turn("q", "a")
        assert session.turn_id == 1
        session.add_turn("q2", "a2")
        assert session.turn_id == 2

    def test_metrics_logged_with_correct_turn_id(self, tmp_path, mocker):
        db_path = str(tmp_path / "turn_metrics.db")
        from src.metrics.store import MetricsStore
        metrics = MetricsStore(db_path)

        from src.engine import DAGEngine, ToolRegistry
        from src.session.data import SessionData

        registry = ToolRegistry()
        registry.register("llm", lambda c, s: {"text": f"answer_{s.turn_id}"})

        app_config = mocker.MagicMock()
        app_config.session = None
        app_config.workflows = {
            "wf": {
                "_product": "default",
                "return_mode": "full",
                "nodes": [
                    {"name": "llm_node", "next_type": "one", "next": ""},
                ],
            }
        }
        app_config.node_config = lambda key: {"tool": "llm"}

        engine = DAGEngine(tools=registry, app_config=app_config, metrics_store=metrics)

        session = SessionData()
        engine.run("wf", {"query": "q1"}, session)
        engine.run("wf", {"query": "q2"}, session)

        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT turn_id FROM runs ORDER BY id"
        ).fetchall()
        conn.close()
        assert rows[0][0] == 0
        assert rows[1][0] == 1

    def test_run_without_metrics_store_still_works(self, mocker):
        from src.engine import DAGEngine, ToolRegistry
        from src.session.data import SessionData

        registry = ToolRegistry()
        registry.register("llm", lambda c, s: {"text": "ok"})

        app_config = mocker.MagicMock()
        app_config.session = None
        app_config.workflows = {
            "wf": {
                "_product": "default",
                "return_mode": "full",
                "nodes": [
                    {"name": "node1", "next_type": "one", "next": ""},
                ],
            }
        }
        app_config.node_config = lambda key: {"tool": "llm"}

        engine = DAGEngine(tools=registry, app_config=app_config)
        session = SessionData()
        result = engine.run("wf", {"query": "test"}, session)
        assert session.turn_id == 1
        assert isinstance(result, SessionData)

    def test_node_error_isolated_not_crashing(self, tmp_path, mocker):
        """W1-3: 单节点抛错不应崩溃整条 DAG，且 run/node 状态记为 error。"""
        db_path = str(tmp_path / "err_metrics.db")
        from src.metrics.store import MetricsStore
        metrics = MetricsStore(db_path)

        from src.engine import DAGEngine, ToolRegistry
        from src.session.data import SessionData

        def boom(_c, _s):
            raise RuntimeError("tool blew up")

        registry = ToolRegistry()
        registry.register("llm", boom)

        app_config = mocker.MagicMock()
        app_config.session = None
        app_config.workflows = {
            "wf": {
                "_product": "default",
                "return_mode": "full",
                "nodes": [{"name": "n1", "next_type": "one", "next": ""}],
            }
        }
        app_config.node_config = lambda key: {"tool": "llm"}

        engine = DAGEngine(tools=registry, app_config=app_config, metrics_store=metrics)
        session = SessionData()
        # 不应抛异常
        engine.run("wf", {"query": "hi"}, session)

        conn = sqlite3.connect(db_path)
        run = conn.execute("SELECT status, error_message FROM runs").fetchone()
        node = conn.execute(
            "SELECT status, error_message FROM node_logs WHERE node_name='n1'"
        ).fetchone()
        conn.close()
        assert run[0] == "error"
        assert "tool blew up" in (run[1] or "")
        assert node[0] == "error"
        assert "RuntimeError" in (node[1] or "")

    def test_prometheus_failure_isolated(self, tmp_path, mocker):
        """Prometheus 指标记录失败不应对 DAG 执行产生影响。"""
        db_path = str(tmp_path / "prom_metrics.db")
        from src.metrics.store import MetricsStore
        metrics = MetricsStore(db_path)

        from src.engine import DAGEngine, ToolRegistry
        from src.session.data import SessionData

        registry = ToolRegistry()
        registry.register("llm", lambda c, s: {"text": "ok"})

        app_config = mocker.MagicMock()
        app_config.session = None
        app_config.workflows = {
            "wf": {
                "_product": "default",
                "return_mode": "full",
                "nodes": [{"name": "n1", "next_type": "one", "next": ""}],
            }
        }
        app_config.node_config = lambda key: {"tool": "llm"}

        def blowup(*_a, **_kw): raise RuntimeError("metrics down")
        mocker.patch("src.metrics.prometheus.record_node_metric", side_effect=blowup)
        mocker.patch("src.metrics.prometheus.record_workflow_run", side_effect=blowup)

        engine = DAGEngine(tools=registry, app_config=app_config, metrics_store=metrics)
        session = SessionData()
        engine.run("wf", {"query": "test"}, session)

        conn = sqlite3.connect(db_path)
        run = conn.execute("SELECT status FROM runs").fetchone()
        conn.close()
        assert run[0] == "ok"  # Prometheus 失败不影响运行状态
        assert session.turn_id == 1

    def test_rag_capture_on_metrics(self, tmp_path, mocker):
        """rag_search 节点的检索结果应在 _collect_metrics 中入库。"""
        db_path = str(tmp_path / "rag_cap.db")
        from src.metrics.store import MetricsStore
        metrics = MetricsStore(db_path)

        from src.engine import DAGEngine, ToolRegistry
        from src.session.data import SessionData

        registry = ToolRegistry()
        registry.register("rag_search", lambda _c, _s: {
            "text": "context", "chunks": ["c1", "c2"],
            "results": [
                {"score": 0.9, "payload": {"text": "隔热膜...", "source": "kb.md"}},
                {"score": 0.5, "payload": {"text": "车衣...", "source": "kb2.md"}},
            ],
        })

        app_config = mocker.MagicMock()
        app_config.session = None
        app_config.workflows = {
            "wf": {
                "_product": "default", "return_mode": "full",
                "nodes": [{"name": "search_kb", "next_type": "one", "next": ""}],
            }
        }
        app_config.node_config = lambda key: {"tool": "rag_search"}
        engine = DAGEngine(tools=registry, app_config=app_config, metrics_store=metrics)
        session = SessionData()
        engine.run("wf", {"query": "test"}, session)

        import sqlite3
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT score, source, chunk_preview FROM rag_retrievals ORDER BY score DESC"
        ).fetchall()
        conn.close()
        assert len(rows) == 2
        assert rows[0][0] == 0.9
        assert rows[0][1] == "kb.md"
        assert "隔热膜" in rows[0][2]
