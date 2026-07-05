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
