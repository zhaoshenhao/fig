from __future__ import annotations

import sys
from pathlib import Path

import pytest

_proj_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_proj_root))


class TestDAGEngineOneChain:
    def test_basic_one_chain(self, temp_config_dir, mock_tools):
        from src.config import load_app_config
        from src.engine.dag import DAGEngine

        app_cfg = load_app_config(temp_config_dir)
        engine = DAGEngine(tools=mock_tools, app_config=app_cfg)
        result = engine.run("default", {"query": "hello"})

        assert result is not None
        nodes = result["nodes"]
        assert len(nodes) >= 3
        assert nodes[0]["name"] == "input"
        assert nodes[-1]["name"] == "output"
        node_names = [n["name"] for n in nodes]
        assert "retrieve" in node_names
        assert "generate" in node_names

    def test_workflow_not_found(self, temp_config_dir, mock_tools):
        from src.config import load_app_config
        from src.engine.dag import DAGEngine

        app_cfg = load_app_config(temp_config_dir)
        engine = DAGEngine(tools=mock_tools, app_config=app_cfg)

        with pytest.raises(KeyError, match="not found"):
            engine.run("bogus", {"query": "x"})

    def test_empty_nodes(self, temp_config_dir, mock_tools):
        from src.config import load_app_config
        from src.engine.dag import DAGEngine

        app_cfg = load_app_config(temp_config_dir)
        app_cfg.workflows["empty"] = {
            "name": "empty",
            "return_mode": "full",
            "nodes": [],
        }
        engine = DAGEngine(tools=mock_tools, app_config=app_cfg)

        result = engine.run("empty", {"query": "x"})
        nodes = result["nodes"]
        assert nodes[0]["name"] == "input"
        assert nodes[-1]["name"] == "output"

    def test_unknown_tool_raises(self, temp_config_dir):
        from src.config import load_app_config
        from src.engine.dag import DAGEngine
        from src.engine.tool import ToolRegistry

        app_cfg = load_app_config(temp_config_dir)
        engine = DAGEngine(tools=ToolRegistry(), app_config=app_cfg)

        with pytest.raises(ValueError, match="unknown tool"):
            engine.run("default", {"query": "x"})

    def test_return_mode_full(self, temp_config_dir, mock_tools):
        from src.config import load_app_config
        from src.engine.dag import DAGEngine

        app_cfg = load_app_config(temp_config_dir)
        engine = DAGEngine(tools=mock_tools, app_config=app_cfg)
        result = engine.run("default", {"query": "hello"})

        assert "chat_id" in result
        assert "nodes" in result
        assert "created_at" in result

    def test_return_mode_last(self, temp_config_dir, mock_tools):
        from src.config import load_app_config
        from src.engine.dag import DAGEngine

        app_cfg = load_app_config(temp_config_dir)
        engine = DAGEngine(tools=mock_tools, app_config=app_cfg)
        result = engine.run("last_mode_wf", {"query": "hello"})

        assert "chat_id" in result
        assert result["return_mode"] == "last"
        assert result["nodes"][-1]["name"] == "output"


class TestDAGRouting:
    def test_if_then_routing(self, temp_config_dir, mock_tools):
        from src.config import load_app_config
        from src.engine.dag import DAGEngine

        app_cfg = load_app_config(temp_config_dir)
        engine = DAGEngine(tools=mock_tools, app_config=app_cfg)
        result = engine.run("if_then_wf", {"query": "hello world"})

        nodes = result["nodes"]
        node_names = [n["name"] for n in nodes]
        assert "greet" in node_names

    def test_switch_serial(self, temp_config_dir, mock_tools):
        from src.config import load_app_config
        from src.engine.dag import DAGEngine

        app_cfg = load_app_config(temp_config_dir)
        engine = DAGEngine(tools=mock_tools, app_config=app_cfg)
        result = engine.run("switch_wf", {"query": "test"})

        nodes = result["nodes"]
        node_names = [n["name"] for n in nodes]
        assert "branch_a" in node_names
        assert "branch_b" in node_names

    def test_switch_parallel(self, temp_config_dir, mock_tools):
        from src.config import load_app_config
        from src.engine.dag import DAGEngine

        app_cfg = load_app_config(temp_config_dir)
        engine = DAGEngine(tools=mock_tools, app_config=app_cfg)
        result = engine.run("switch_parallel_wf", {"query": "test"})

        nodes = result["nodes"]
        node_names = [n["name"] for n in nodes]
        assert "branch_x" in node_names
        assert "branch_y" in node_names
        assert "dispatcher" in node_names
        dispatcher = [n for n in nodes if n["name"] == "dispatcher"][0]
        assert "branches" in dispatcher

    def test_walk_branch_if_then_selects_single(self, mocker):
        """并行/分支上下文内 if-then 应按 branch 选择单一路径，而非全部执行。"""
        from src.engine import DAGEngine, ToolRegistry

        reg = ToolRegistry()
        reg.register("router", lambda c, s: {"text": "", "branch": "A"})
        reg.register("llm", lambda c, s: {"text": "ok"})

        app = mocker.MagicMock()
        app.node_config = lambda key: (
            {"tool": "router"} if key.endswith("route") else {"tool": "llm"}
        )
        eng = DAGEngine(tools=reg, app_config=app)
        node_map = {
            "route": {"name": "route", "next_type": "if-then", "next": ["A", "B"]},
            "A": {"name": "A", "next_type": "one", "next": ""},
            "B": {"name": "B", "next_type": "one", "next": ""},
        }
        result = eng._walk_branch("route", node_map, product="p")
        names = [n["name"] for n in result]
        assert "route" in names
        assert "A" in names
        assert "B" not in names  # 未命中的分支不应执行


class TestDAGInit:
    def test_auto_registers_tools_when_no_registry(self, temp_config_dir):
        from src.config import load_app_config
        from src.engine.dag import DAGEngine

        app_cfg = load_app_config(temp_config_dir)
        engine = DAGEngine(app_config=app_cfg)

        assert engine._tools.get("llm") is not None
        assert engine._tools.get("rag_search") is not None
        assert engine._tools.get("router") is not None

    def test_uses_provided_registry(self, temp_config_dir, mock_tools):
        from src.config import load_app_config
        from src.engine.dag import DAGEngine

        app_cfg = load_app_config(temp_config_dir)
        engine = DAGEngine(tools=mock_tools, app_config=app_cfg)

        assert engine._tools.get("mock_search") is not None

    def test_falls_back_to_get_app_config(self, temp_config_dir, mock_tools):
        import src.config as cfg_mod

        cfg_mod.load_app_config(temp_config_dir)
        from src.engine.dag import DAGEngine

        engine = DAGEngine(tools=mock_tools)
        assert engine._app_config is cfg_mod.get_app_config()


class TestMetrics:
    def test_metrics_tracking(self, temp_config_dir, mock_tools):
        from src.config import load_app_config
        from src.engine.dag import DAGEngine

        app_cfg = load_app_config(temp_config_dir)
        engine = DAGEngine(tools=mock_tools, app_config=app_cfg)
        result = engine.run("metrics_wf", {"query": "test"})

        step_nodes = [n for n in result["nodes"] if n["name"] == "step"]
        assert len(step_nodes) == 1
        assert "metrics" in step_nodes[0]
        assert "total_ms" in step_nodes[0]["metrics"]


class TestNodeConfigMissing:
    def test_missing_node_config_raises(self, temp_config_dir, mock_tools):
        from src.config import load_app_config
        from src.engine.dag import DAGEngine

        app_cfg = load_app_config(temp_config_dir)
        app_cfg.workflows["bad"] = {
            "name": "bad",
            "_product": "default",
            "return_mode": "full",
            "nodes": [
                {"name": "missing_node", "next_type": "one", "next": ""},
            ],
        }
        engine = DAGEngine(tools=mock_tools, app_config=app_cfg)

        with pytest.raises(KeyError, match="not found"):
            engine.run("bad", {"query": "x"})


class TestMultiTurn:
    def test_new_session_has_history_and_turn_record(self, temp_config_dir, mock_tools):
        from src.config import load_app_config
        from src.engine.dag import DAGEngine

        app_cfg = load_app_config(temp_config_dir)
        engine = DAGEngine(tools=mock_tools, app_config=app_cfg)
        result = engine.run("default", {"query": "hello"})

        assert "history" in result
        assert "return_mode" in result
        assert len(result["history"]) == 1
        assert result["history"][0].input == "hello"
        assert result["history"][0].output

    def test_continuation_appends_history(self, temp_config_dir, mock_tools):
        from src.config import load_app_config
        from src.engine.dag import DAGEngine

        app_cfg = load_app_config(temp_config_dir)
        engine = DAGEngine(tools=mock_tools, app_config=app_cfg)

        result1 = engine.run("default", {"query": "first question"})
        session = result1
        assert len(session["history"]) == 1

        engine.run("default", {"query": "follow up"}, session=session)

        assert len(session["history"]) == 2
        assert session["history"][0].input == "first question"
        assert session["history"][1].input == "follow up"

    def test_multi_turn_keeps_chat_id(self, temp_config_dir, mock_tools):
        from src.config import load_app_config
        from src.engine.dag import DAGEngine

        app_cfg = load_app_config(temp_config_dir)
        engine = DAGEngine(tools=mock_tools, app_config=app_cfg)

        result1 = engine.run("default", {"query": "turn 1"})
        cid = result1["chat_id"]

        result2 = engine.run("default", {"query": "turn 2"}, session=result1)
        assert result2["chat_id"] == cid

    def test_multi_turn_accumulates_nodes(self, temp_config_dir, mock_tools):
        from src.config import load_app_config
        from src.engine.dag import DAGEngine

        app_cfg = load_app_config(temp_config_dir)
        engine = DAGEngine(tools=mock_tools, app_config=app_cfg)

        result1 = engine.run("default", {"query": "q1"})
        node_count_1 = len(result1["nodes"])

        result2 = engine.run("default", {"query": "q2"}, session=result1)
        node_count_2 = len(result2["nodes"])

        assert node_count_2 > node_count_1
        input_nodes = [n for n in result2["nodes"] if n["name"] == "input"]
        assert len(input_nodes) == 2

    def test_multi_turn_last_mode(self, temp_config_dir, mock_tools):
        from src.config import load_app_config
        from src.engine.dag import DAGEngine

        app_cfg = load_app_config(temp_config_dir)
        engine = DAGEngine(tools=mock_tools, app_config=app_cfg)

        result1 = engine.run("last_mode_wf", {"query": "q1"})
        assert "chat_id" in result1
        assert result1["return_mode"] == "last"

        result2 = engine.run("last_mode_wf", {"query": "q2"}, session=result1)
        assert result2["chat_id"] == result1["chat_id"]
        assert len(result2["history"]) == 2
