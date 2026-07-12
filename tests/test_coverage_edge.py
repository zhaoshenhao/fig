from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

_proj_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_proj_root))


class TestDAGEdgeCases:
    def test_if_then_default_branch(self, temp_config_dir):
        from src.config import load_app_config
        from src.engine.dag import DAGEngine
        from src.engine.tool import ToolRegistry

        app_cfg = load_app_config(temp_config_dir)

        def mock_return_dict(config, session):
            return {"branch": "nonexistent_target"}

        def mock_echo(config, session):
            return {"text": config.get("message", "")}

        reg = ToolRegistry()
        reg.register("mock_tool", mock_return_dict)
        reg.register("mock_echo", mock_echo)

        app_cfg.nodes["dflt:router_new"] = {
            "tool": "mock_tool",
            "router": {"default": "br_greet"},
        }
        app_cfg.nodes["dflt:br_farewell"] = {"tool": "mock_echo", "message": "bye"}
        app_cfg.nodes["dflt:br_greet"] = {"tool": "mock_echo", "message": "hi"}

        engine = DAGEngine(tools=reg, app_config=app_cfg)

        app_cfg.workflows["if_default"] = {
            "name": "if_default",
            "_product": "dflt",
            "return_mode": "full",
            "nodes": [
                {"name": "router_new", "next_type": "if-then", "next": ["br_greet", "br_farewell"]},
                {"name": "br_greet", "next_type": "one", "next": ""},
                {"name": "br_farewell", "next_type": "one", "next": ""},
            ],
        }
        result = engine.run("if_default", {"query": "test"})
        node_names = [n["name"] for n in result["nodes"]]
        assert "br_greet" in node_names

    def test_if_then_int_result(self, temp_config_dir):
        from src.config import load_app_config
        from src.engine.dag import DAGEngine
        from src.engine.tool import ToolRegistry

        app_cfg = load_app_config(temp_config_dir)

        def mock_return_str(config, session):
            return "br_farewell"

        def mock_echo(config, session):
            return {"text": config.get("message", "")}

        reg = ToolRegistry()
        reg.register("mock_tool", mock_return_str)
        reg.register("mock_echo", mock_echo)

        app_cfg.nodes["dflt:router_str"] = {"tool": "mock_tool"}
        app_cfg.nodes["dflt:br_farewell"] = {"tool": "mock_echo", "message": "bye"}
        app_cfg.nodes["dflt:br_greet"] = {"tool": "mock_echo", "message": "hi"}

        engine = DAGEngine(tools=reg, app_config=app_cfg)

        app_cfg.workflows["if_str"] = {
            "name": "if_str",
            "_product": "dflt",
            "return_mode": "full",
            "nodes": [
                {"name": "router_str", "next_type": "if-then", "next": ["br_greet", "br_farewell"]},
                {"name": "br_greet", "next_type": "one", "next": ""},
                {"name": "br_farewell", "next_type": "one", "next": ""},
            ],
        }
        result = engine.run("if_str", {"query": "test"})
        node_names = [n["name"] for n in result["nodes"]]
        assert "br_farewell" in node_names

    def test_auto_register_builtins_creates_registry(self):
        from src.engine.dag import DAGEngine

        engine = DAGEngine()
        assert engine._tools.get("llm") is not None
        assert engine._tools.get("rag_search") is not None
        assert engine._tools.get("router") is not None

    def test_provided_registry_preserves_tools(self, temp_config_dir):
        from src.config import load_app_config
        from src.engine.dag import DAGEngine
        from src.engine.tool import ToolRegistry

        app_cfg = load_app_config(temp_config_dir)
        reg = ToolRegistry()
        reg.register("custom", lambda c, s: {})

        engine = DAGEngine(tools=reg, app_config=app_cfg)
        assert engine._tools.get("custom") is not None
        assert engine._tools.get("llm") is None


class TestConfigEdgeCases:
    def test_llm_config_get_key_error(self, temp_config_dir):
        from src.config import LLMConfig, LLMProvider

        cfg = LLMConfig(default="openai", providers={
            "openai": LLMProvider(
                type="openai", base_url="https://x.com", api_key="k", model="m"
            )
        })
        with pytest.raises(KeyError, match="not found"):
            cfg.get("nonexistent")

    def test_app_config_reset_global(self, temp_config_dir, monkeypatch):
        import src.config as cfg_mod

        cfg_mod.load_app_config(temp_config_dir)
        cfg1 = cfg_mod.get_app_config()

        monkeypatch.setattr(cfg_mod, "_APP_CONFIG", None)
        with pytest.raises(RuntimeError, match="not loaded"):
            cfg_mod.get_app_config()

        cfg_mod._APP_CONFIG = cfg1

    def test_get_workflow_missing_in_existing_dir(self, temp_config_dir):
        from src.config import get_workflow

        with pytest.raises(KeyError, match="not found"):
            get_workflow(temp_config_dir, "nonexistent")

    def test_load_app_config_missing_embed_file(self, tmp_path):
        cfg = tmp_path / "config"
        wp = cfg / "workflows"
        pd = wp / "default"
        nd = pd / "nodes"
        nd.mkdir(parents=True)

        (cfg / "llm.yaml").write_text(
            yaml.dump({
                "default": "o",
                "providers": {
                    "o": {"type": "openai", "base_url": "https://x.com", "model": "m"}
                }
            }),
            encoding="utf-8",
        )
        (pd / "workflow.yaml").write_text(
            yaml.dump({"name": "default", "nodes": []}),
            encoding="utf-8",
        )

        from src.config import load_app_config

        cfg_obj = load_app_config(cfg)
        assert cfg_obj.embed is None

    def test_load_app_config_with_empty_workflows_dir(self, tmp_path):
        cfg = tmp_path / "config"
        cfg.mkdir()
        wp = cfg / "workflows"
        wp.mkdir()

        (cfg / "llm.yaml").write_text(
            yaml.dump({
                "default": "o",
                "providers": {
                    "o": {"type": "openai", "base_url": "https://x.com", "model": "m"}
                }
            }),
            encoding="utf-8",
        )
        (cfg / "embed.yaml").write_text(
            yaml.dump({
                "default": "o",
                "providers": {
                    "o": {"type": "openai", "base_url": "https://x.com", "model": "m", "dims": 768}
                }
            }),
            encoding="utf-8",
        )

        from src.config import load_app_config

        cfg_obj = load_app_config(cfg)
        assert cfg_obj.nodes == {}
        assert cfg_obj.workflows == {}

    def test_wf_collections(self, temp_config_dir):
        from src.config import load_app_config

        cfg = load_app_config(temp_config_dir)
        cols = cfg.wf_collections("default")
        assert "default" in cols

    def test_wf_collections_unknown_workflow(self, temp_config_dir):
        from src.config import load_app_config

        cfg = load_app_config(temp_config_dir)
        with pytest.raises(KeyError, match="not found"):
            cfg.wf_collections("nonexistent")


# ============================================================
# New tests below — appended for coverage
# ============================================================


class TestLoggingConfig:
    def test_logging_config_defaults(self):
        from src.config import LoggingConfig

        cfg = LoggingConfig()
        assert cfg.level == "INFO"
        assert cfg.format == "json"
        assert cfg.output == "stdout"

    def test_logging_config_custom(self):
        from src.config import LoggingConfig

        cfg = LoggingConfig(level="DEBUG", format="text", output="stderr")
        assert cfg.level == "DEBUG"
        assert cfg.format == "text"
        assert cfg.output == "stderr"


class TestLoadConfigFunctions:
    def test_load_db_config(self, tmp_path):
        cfg_dir = tmp_path / "cfg"
        cfg_dir.mkdir()
        (cfg_dir / "db.yaml").write_text(
            yaml.dump({
                "default": "mysql_main",
                "pools": {
                    "mysql_main": {
                        "type": "mysql", "host": "h", "port": 3307,
                        "user": "u", "password": "p", "database": "d", "pool_size": 3,
                    },
                },
            }),
            encoding="utf-8",
        )
        from src.config import _load_db_config

        result = _load_db_config(cfg_dir)
        assert result.default == "mysql_main"
        assert result.pools["mysql_main"].port == 3307
        assert result.pools["mysql_main"].pool_size == 3

    def test_load_db_config_defaults(self, tmp_path):
        cfg_dir = tmp_path / "cfg"
        cfg_dir.mkdir()
        (cfg_dir / "db.yaml").write_text(
            yaml.dump({"default": "pg", "pools": {"pg": {"type": "postgresql"}}}),
            encoding="utf-8",
        )
        from src.config import _load_db_config

        result = _load_db_config(cfg_dir)
        pool = result.pools["pg"]
        assert pool.host == "localhost"
        assert pool.port == 5432
        assert pool.user == ""
        assert pool.password == ""
        assert pool.database == ""
        assert pool.pool_size == 5

    def test_load_session_config(self, tmp_path):
        cfg_dir = tmp_path / "cfg"
        cfg_dir.mkdir()
        (cfg_dir / "session.yaml").write_text(
            yaml.dump({
                "store": "redis",
                "max_age": 7200,
                "max_turns": 50,
                "max_chars": 50000,
                "keep": 10,
                "compress_max_words": 2000,
                "cleanup_interval": 600,
                "memory": {"max_sessions": 5000},
                "redis": {"url": "redis://x:6379/2", "prefix": "pfx:"},
                "summary": {
                    "base_url": "http://s", "api_key": "ak", "model": "m",
                    "system_prompt": "sp {max_words}",
                },
            }),
            encoding="utf-8",
        )
        from src.config import _load_session_config

        result = _load_session_config(cfg_dir)
        assert result.store == "redis"
        assert result.max_age == 7200
        assert result.max_turns == 50
        assert result.max_chars == 50000
        assert result.keep == 10
        assert result.compress_max_words == 2000
        assert result.cleanup_interval == 600
        assert result.memory_max_sessions == 5000
        assert result.redis_url == "redis://x:6379/2"
        assert result.redis_prefix == "pfx:"
        assert result.summary.base_url == "http://s"
        assert result.summary.api_key == "ak"
        assert result.summary.model == "m"
        assert result.summary.system_prompt == "sp {max_words}"

    def test_load_auth_config(self, tmp_path):
        cfg_dir = tmp_path / "cfg"
        cfg_dir.mkdir()
        (cfg_dir / "auth.yaml").write_text(
            yaml.dump({"api_keys": ["k1", "k2"], "skip_paths": ["/health", "/docs"]}),
            encoding="utf-8",
        )
        from src.config import _load_auth_config

        result = _load_auth_config(cfg_dir)
        assert result.api_keys == ["k1", "k2"]
        assert result.skip_paths == ["/health", "/docs"]

    def test_load_logging_config(self, tmp_path):
        cfg_dir = tmp_path / "cfg"
        cfg_dir.mkdir()
        (cfg_dir / "logging.yaml").write_text(
            yaml.dump({"level": "DEBUG", "format": "text", "output": "stderr"}),
            encoding="utf-8",
        )
        from src.config import _load_logging_config

        result = _load_logging_config(cfg_dir)
        assert result.level == "DEBUG"
        assert result.format == "text"
        assert result.output == "stderr"

    def test_load_logging_config_defaults(self, tmp_path):
        cfg_dir = tmp_path / "cfg"
        cfg_dir.mkdir()
        (cfg_dir / "logging.yaml").write_text("{}", encoding="utf-8")
        from src.config import _load_logging_config

        result = _load_logging_config(cfg_dir)
        assert result.level == "INFO"
        assert result.format == "json"
        assert result.output == "stdout"


class TestInitEnv:
    def test_init_env_import_error(self, monkeypatch):
        import builtins

        orig = builtins.__import__

        def mock_imp(name, *a, **kw):
            if "dotenv" in name:
                raise ImportError("no dotenv")
            return orig(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", mock_imp)
        from src.config import _init_env

        _init_env(".env")


class TestConfigWorkflowEdgeCases:
    def test_skip_file_and_missing_wf_yaml(self, tmp_path):
        cfg_dir = tmp_path / "config"
        wp = cfg_dir / "workflows"
        wp.mkdir(parents=True)
        (wp / "file.txt").write_text("not a dir", encoding="utf-8")

        pd = wp / "valid"
        nd = pd / "nodes"
        nd.mkdir(parents=True)
        (pd / "workflow.yaml").write_text(
            yaml.dump({"name": "valid", "nodes": []}), encoding="utf-8",
        )

        missing = wp / "no_wf"
        missing.mkdir()

        (cfg_dir / "llm.yaml").write_text(
            yaml.dump({"default": "o", "providers": {
                "o": {"type": "openai", "base_url": "x", "model": "m"},
            }}),
            encoding="utf-8",
        )
        (cfg_dir / "embed.yaml").write_text(
            yaml.dump({"default": "o", "providers": {
                "o": {"type": "openai", "base_url": "x", "model": "m", "dims": 768},
            }}),
            encoding="utf-8",
        )

        from src.config import load_app_config

        cfg = load_app_config(cfg_dir)
        assert "valid" in cfg.workflows
        assert "no_wf" not in cfg.workflows

    def test_load_with_all_optional_configs(self, tmp_path):
        cfg_dir = tmp_path / "config"
        wp = cfg_dir / "workflows"
        wp.mkdir(parents=True)

        (cfg_dir / "db.yaml").write_text(
            yaml.dump({"default": "m", "pools": {"m": {"type": "mysql"}}}),
            encoding="utf-8",
        )
        (cfg_dir / "session.yaml").write_text(
            yaml.dump({"store": "memory"}), encoding="utf-8",
        )
        (cfg_dir / "auth.yaml").write_text(
            yaml.dump({"api_keys": ["k"]}), encoding="utf-8",
        )
        (cfg_dir / "logging.yaml").write_text(
            yaml.dump({"level": "WARNING"}), encoding="utf-8",
        )
        (cfg_dir / "llm.yaml").write_text(
            yaml.dump({"default": "o", "providers": {
                "o": {"type": "openai", "base_url": "x", "model": "m"},
            }}),
            encoding="utf-8",
        )
        (cfg_dir / "embed.yaml").write_text(
            yaml.dump({"default": "o", "providers": {
                "o": {"type": "openai", "base_url": "x", "model": "m", "dims": 768},
            }}),
            encoding="utf-8",
        )

        from src.config import load_app_config

        cfg = load_app_config(cfg_dir)
        assert cfg.db is not None
        assert cfg.db.default == "m"
        assert cfg.session is not None
        assert cfg.auth.api_keys == ["k"]
        assert cfg.logging.level == "WARNING"


class TestDAGMoreEdges:
    def test_trim_with_session_config(self, temp_config_dir):
        (temp_config_dir / "session.yaml").write_text(
            yaml.dump({"store": "memory", "max_turns": 100, "keep": 2}),
            encoding="utf-8",
        )
        from src.config import load_app_config
        from src.engine.dag import DAGEngine
        from src.engine.tool import ToolRegistry
        from src.session.data import SessionData

        app_cfg = load_app_config(temp_config_dir)

        def mock_echo(config, session):
            return {"text": "ok"}

        reg = ToolRegistry()
        reg.register("mock_echo", mock_echo)
        app_cfg.nodes["dflt:echo"] = {"tool": "mock_echo"}
        app_cfg.workflows["trim_wf"] = {
            "name": "trim_wf", "_product": "dflt", "return_mode": "full",
            "nodes": [{"name": "echo", "next_type": "one", "next": ""}],
        }
        engine = DAGEngine(tools=reg, app_config=app_cfg)
        session = SessionData()
        session["nodes"] = [{"name": "input", "data": {"text": "hi"}}]
        result = engine.run("trim_wf", {"query": "hi"}, session)
        assert "nodes" in result

    def test_walk_empty_node_name(self, temp_config_dir):
        from src.config import load_app_config
        from src.engine.dag import DAGEngine
        from src.engine.tool import ToolRegistry

        app_cfg = load_app_config(temp_config_dir)

        def mock_echo(config, session):
            return {"text": "ok"}

        reg = ToolRegistry()
        reg.register("mock_echo", mock_echo)
        app_cfg.nodes["dflt:start"] = {"tool": "mock_echo"}
        app_cfg.nodes["dflt:real"] = {"tool": "mock_echo"}

        engine = DAGEngine(tools=reg, app_config=app_cfg)
        app_cfg.workflows["empty_name_wf"] = {
            "name": "empty_name_wf", "_product": "dflt", "return_mode": "full",
            "nodes": [
                {"name": "start", "next_type": "switch",
                 "next": ["", "real"], "parallel": False},
                {"name": "real", "next_type": "one", "next": ""},
            ],
        }
        result = engine.run("empty_name_wf", {"query": "x"})
        assert "nodes" in result

    def test_walk_unknown_node_def(self, temp_config_dir):
        from src.config import load_app_config
        from src.engine.dag import DAGEngine
        from src.engine.tool import ToolRegistry

        app_cfg = load_app_config(temp_config_dir)

        def mock_echo(config, session):
            return {"text": "ok"}

        reg = ToolRegistry()
        reg.register("mock_echo", mock_echo)
        app_cfg.nodes["dflt:start"] = {"tool": "mock_echo"}

        engine = DAGEngine(tools=reg, app_config=app_cfg)
        app_cfg.workflows["unknown_def_wf"] = {
            "name": "unknown_def_wf", "_product": "dflt", "return_mode": "full",
            "nodes": [
                {"name": "start", "next_type": "one", "next": "ghost"},
            ],
        }
        result = engine.run("unknown_def_wf", {"query": "x"})
        assert "nodes" in result

    def test_find_pre_returns_none(self):
        from src.engine.dag import DAGEngine
        from src.engine.tool import ToolRegistry

        engine = DAGEngine(tools=ToolRegistry())
        session = {"nodes": []}
        node_map = {}
        result = engine._find_pre(session, "sole_node", node_map)
        assert result is None

    def test_find_pre_all_same_name_returns_none(self):
        from src.engine.dag import DAGEngine
        from src.engine.tool import ToolRegistry

        engine = DAGEngine(tools=ToolRegistry())
        session = {"nodes": [{"name": "sole_node", "data": {"text": ""}}]}
        node_map = {}
        result = engine._find_pre(session, "sole_node", node_map)
        assert result is None

    def test_walk_branch_keyerror_node_config(self, temp_config_dir):
        from src.config import load_app_config
        from src.engine.dag import DAGEngine
        from src.engine.tool import ToolRegistry
        from src.session.data import SessionData

        app_cfg = load_app_config(temp_config_dir)

        def mock_echo(config, session):
            return {"text": "ok"}

        reg = ToolRegistry()
        reg.register("mock_echo", mock_echo)
        app_cfg.nodes["dflt:sw"] = {"tool": "mock_echo"}

        engine = DAGEngine(tools=reg, app_config=app_cfg)
        app_cfg.workflows["branch_keyerr_wf"] = {
            "name": "branch_keyerr_wf", "_product": "bad_product",
            "return_mode": "full",
            "nodes": [
                {"name": "sw", "next_type": "switch",
                 "next": ["ghost"], "parallel": True},
            ],
        }
        session = SessionData()
        session["nodes"] = [{"name": "input", "data": {"text": "x"}}]
        with pytest.raises(KeyError, match="not found"):
            engine.run("branch_keyerr_wf", {"query": "x"}, session)

    def test_walk_branch_valueerror_tool(self, temp_config_dir):
        from src.config import load_app_config
        from src.engine.dag import DAGEngine
        from src.engine.tool import ToolRegistry
        from src.session.data import SessionData

        app_cfg = load_app_config(temp_config_dir)
        reg = ToolRegistry()
        app_cfg.nodes["dflt:sw"] = {"tool": "unknown_tool"}

        engine = DAGEngine(tools=reg, app_config=app_cfg)
        app_cfg.workflows["branch_valerr_wf"] = {
            "name": "branch_valerr_wf", "_product": "dflt", "return_mode": "full",
            "nodes": [
                {"name": "sw", "next_type": "switch",
                 "next": ["ghost"], "parallel": True},
            ],
        }
        session = SessionData()
        session["nodes"] = [{"name": "input", "data": {"text": "x"}}]
        with pytest.raises(ValueError, match="unknown tool"):
            engine.run("branch_valerr_wf", {"query": "x"}, session)

    def test_walk_branch_string_result(self, temp_config_dir):
        from src.config import load_app_config
        from src.engine.dag import DAGEngine
        from src.engine.tool import ToolRegistry

        app_cfg = load_app_config(temp_config_dir)

        def mock_return_str(config, session):
            return "branch_x"

        def mock_echo(config, session):
            return {"text": "ok"}

        reg = ToolRegistry()
        reg.register("mock_str", mock_return_str)
        reg.register("mock_echo", mock_echo)
        app_cfg.nodes["dflt:sw"] = {"tool": "mock_str"}
        app_cfg.nodes["dflt:branch_x"] = {"tool": "mock_echo"}

        engine = DAGEngine(tools=reg, app_config=app_cfg)
        app_cfg.workflows["branch_str_wf"] = {
            "name": "branch_str_wf", "_product": "dflt", "return_mode": "full",
            "nodes": [
                {"name": "sw", "next_type": "switch",
                 "next": ["branch_x"], "parallel": True},
                {"name": "branch_x", "next_type": "one", "next": ""},
            ],
        }
        result = engine.run("branch_str_wf", {"query": "x"})
        assert "nodes" in result

    def test_walk_branch_switch_list_next(self, temp_config_dir):
        from src.config import load_app_config
        from src.engine.dag import DAGEngine
        from src.engine.tool import ToolRegistry

        app_cfg = load_app_config(temp_config_dir)

        def mock_echo(config, session):
            return {"text": "ok"}

        reg = ToolRegistry()
        reg.register("mock_echo", mock_echo)
        app_cfg.nodes["dflt:sw"] = {"tool": "mock_echo"}
        app_cfg.nodes["dflt:a"] = {"tool": "mock_echo"}
        app_cfg.nodes["dflt:b"] = {"tool": "mock_echo"}

        engine = DAGEngine(tools=reg, app_config=app_cfg)
        app_cfg.workflows["branch_list_wf"] = {
            "name": "branch_list_wf", "_product": "dflt", "return_mode": "full",
            "nodes": [
                {"name": "sw", "next_type": "switch",
                 "next": ["a", "b"], "parallel": True},
                {"name": "a", "next_type": "one", "next": ""},
                {"name": "b", "next_type": "one", "next": ""},
            ],
        }
        result = engine.run("branch_list_wf", {"query": "x"})
        node_names = [n["name"] for n in result["nodes"]]
        assert "a" in node_names
        assert "b" in node_names

    def test_walk_branch_empty_and_unknown_names(self, temp_config_dir):
        from src.config import load_app_config
        from src.engine.dag import DAGEngine
        from src.engine.tool import ToolRegistry

        app_cfg = load_app_config(temp_config_dir)

        def mock_echo(config, session):
            return {"text": "ok"}

        reg = ToolRegistry()
        reg.register("mock_echo", mock_echo)
        app_cfg.nodes["dflt:sw"] = {"tool": "mock_echo"}
        app_cfg.nodes["dflt:good"] = {"tool": "mock_echo"}

        engine = DAGEngine(tools=reg, app_config=app_cfg)
        app_cfg.workflows["branch_edges_wf"] = {
            "name": "branch_edges_wf", "_product": "dflt", "return_mode": "full",
            "nodes": [
                {"name": "sw", "next_type": "switch",
                 "next": ["", "good", "ghost"], "parallel": True},
                {"name": "good", "next_type": "one", "next": ""},
            ],
        }
        result = engine.run("branch_edges_wf", {"query": "x"})
        node_names = [n["name"] for n in result["nodes"]]
        assert "good" in node_names


class TestApiCallSuccess:
    def test_successful_call(self, monkeypatch):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "api response text"
        mock_response.raise_for_status = MagicMock()

        def mock_request(method, url, headers=None, json=None, timeout=None):
            return mock_response

        monkeypatch.setattr("httpx2.request", mock_request)

        from src.engine.tools.api_call import api_call
        from src.session.data import SessionData

        config = {
            "url": "http://api.example.com/data",
            "method": "GET",
            "headers": {"X-Key": "val"},
            "timeout": 10,
        }
        session = SessionData()
        result = api_call(config, session)
        assert result["text"] == "api response text"
        assert result["status_code"] == 200

    def test_api_call_exception(self, monkeypatch):
        def mock_request(method, url, headers=None, json=None, timeout=None):
            raise Exception("connection error")

        monkeypatch.setattr("httpx2.request", mock_request)

        from src.engine.tools.api_call import api_call
        from src.session.data import SessionData

        result = api_call({"url": "http://fail.example.com"}, SessionData())
        assert result["text"] == ""
        assert "connection error" in result["error"]


class TestWebSearchDuckDuckGo:
    def test_search_success(self, monkeypatch):
        mock_response = MagicMock()
        mock_response.text = (
            '<div class="result">'
            '<a class="result__a" href="http://example.com">Example Title</a>'
            '<a class="result__snippet">This is a snippet</a>'
            '</div>'
            '<div class="result">'
            '<a class="result__a" href="http://example2.com">Second Title</a>'
            '<a class="result__snippet">Second snippet</a>'
            '</div>'
        )

        def mock_post(url, data=None, headers=None, timeout=None):
            return mock_response

        monkeypatch.setattr("httpx2.post", mock_post)

        from src.engine.tools.web_search import web_search
        from src.session.data import SessionData

        config = {"engine": "duckduckgo", "query_template": "{{query}}", "limit": 5}
        session = SessionData()
        session.nodes = [{"name": "input", "data": {"text": "test search"}}]
        result = web_search(config, session)
        assert "Example Title" in result["text"]
        assert len(result["results"]) == 2

    def test_search_no_results(self, monkeypatch):
        mock_response = MagicMock()
        mock_response.text = "<html><body>no results here</body></html>"

        def mock_post(url, data=None, headers=None, timeout=None):
            return mock_response

        monkeypatch.setattr("httpx2.post", mock_post)

        from src.engine.tools.web_search import web_search
        from src.session.data import SessionData

        config = {"engine": "duckduckgo", "query_template": "{{query}}"}
        session = SessionData()
        session.nodes = [{"name": "input", "data": {"text": "no match"}}]
        result = web_search(config, session)
        assert "no results" in result["text"]
        assert result["results"] == []

    def test_search_http_error(self, monkeypatch):
        def mock_post(url, data=None, headers=None, timeout=None):
            raise Exception("network error")

        monkeypatch.setattr("httpx2.post", mock_post)

        from src.engine.tools.web_search import web_search
        from src.session.data import SessionData

        config = {"engine": "duckduckgo", "query_template": "{{query}}"}
        session = SessionData()
        session.nodes = [{"name": "input", "data": {"text": "fail"}}]
        result = web_search(config, session)
        assert result["text"] == ""
        assert "error" in result
        assert result["results"] == []


class TestDBQuery:
    def test_no_db_name(self):
        from src.engine.tools.db_query import db_query
        from src.session.data import SessionData

        result = db_query({"db": ""}, SessionData())
        assert "no db name" in result["error"]

    def test_db_pool_not_found(self, monkeypatch):
        import sys

        def mock_get_db_pool(name):
            raise KeyError(f"db pool '{name}' not found")

        monkeypatch.setattr(
            sys.modules["src.engine.tools.db_query"], "get_db_pool",
            mock_get_db_pool,
        )

        from src.engine.tools.db_query import db_query
        from src.session.data import SessionData

        result = db_query({"db": "unknown", "query": "SELECT 1"}, SessionData())
        assert "not found" in result["error"]
        assert result["text"] == ""

    def test_successful_query(self, monkeypatch):
        import sys

        mock_pool = MagicMock()
        mock_pool.execute.return_value = [
            {"id": 1, "name": "test"},
            {"id": 2, "name": "other"},
        ]

        def mock_get_db_pool(name):
            return mock_pool

        monkeypatch.setattr(
            sys.modules["src.engine.tools.db_query"], "get_db_pool",
            mock_get_db_pool,
        )

        from src.engine.tools.db_query import db_query
        from src.session.data import SessionData

        result = db_query(
            {"db": "main", "query": "SELECT id, name FROM users"},
            SessionData(),
        )
        assert "id" in result["text"]
        assert "test" in result["text"]
        assert len(result["rows"]) == 2

    def test_query_with_limit(self, monkeypatch):
        import sys

        mock_pool = MagicMock()
        mock_pool.execute.return_value = [{"id": i} for i in range(10)]

        def mock_get_db_pool(name):
            return mock_pool

        monkeypatch.setattr(
            sys.modules["src.engine.tools.db_query"], "get_db_pool",
            mock_get_db_pool,
        )

        from src.engine.tools.db_query import db_query
        from src.session.data import SessionData

        result = db_query(
            {"db": "main", "query": "SELECT id FROM t", "limit": 3},
            SessionData(),
        )
        assert len(result["rows"]) == 3

    def test_query_execution_error(self, monkeypatch):
        import sys

        mock_pool = MagicMock()
        mock_pool.execute.side_effect = Exception("SQL error")

        def mock_get_db_pool(name):
            return mock_pool

        monkeypatch.setattr(
            sys.modules["src.engine.tools.db_query"], "get_db_pool",
            mock_get_db_pool,
        )

        from src.engine.tools.db_query import db_query
        from src.session.data import SessionData

        result = db_query(
            {"db": "main", "query": "SELECT * FROM bad_table"},
            SessionData(),
        )
        assert result["text"] == ""
        assert "SQL error" in result["error"]

    def test_resolve_template(self):
        from src.engine.tools.db_query import _resolve_template
        from src.session.data import SessionData

        session = SessionData()
        session.nodes = [
            {"name": "input", "data": {"text": "my query"}},
            {"name": "extract", "data": {"order_id": "ORD-123"}},
        ]
        session["nodes"] = session.nodes
        session["_workflow"] = "default"
        session["return_mode"] = "full"
        session["long_mem_data"] = "memory text"

        result = _resolve_template(
            "Q: {{query}}, Order: {{order_id}}, Chat: {{chat_id}}, WF: {{_workflow}}",
            session,
        )
        assert "my query" in result
        assert "ORD-123" in result
        assert "default" in result

    def test_resolve_template_no_braces(self):
        from src.engine.tools.db_query import _resolve_template
        from src.session.data import SessionData

        result = _resolve_template("SELECT 1", SessionData())
        assert result == "SELECT 1"

    def test_resolve_template_data_map(self):
        from src.engine.tools.db_query import _resolve_template
        from src.session.data import SessionData

        session = SessionData()
        session.data_map["x"] = "y"
        result = _resolve_template("{{data_map}}", session)
        assert '"x"' in result
        assert '"y"' in result

    def test_format_rows_empty(self):
        from src.engine.tools.db_query import _format_rows

        result = _format_rows([], "mydb")
        assert "0 rows" in result
        assert "mydb" in result

    def test_format_rows_with_data(self):
        from src.engine.tools.db_query import _format_rows

        rows = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        result = _format_rows(rows, "users")
        assert "users" in result
        assert "id" in result
        assert "Alice" in result
        assert "Bob" in result

    def test_no_limit(self, monkeypatch):
        import sys

        mock_pool = MagicMock()
        mock_pool.execute.return_value = [{"id": 1}, {"id": 2}, {"id": 3}]

        def mock_get_db_pool(name):
            return mock_pool

        monkeypatch.setattr(
            sys.modules["src.engine.tools.db_query"], "get_db_pool",
            mock_get_db_pool,
        )

        from src.engine.tools.db_query import db_query
        from src.session.data import SessionData

        result = db_query(
            {"db": "main", "query": "SELECT 1", "limit": 0},
            SessionData(),
        )
        assert len(result["rows"]) == 3


class TestLLMToolHistoryTemplate:
    def test_resolve_history_placeholder(self):
        from src.engine.tools.llm_tool import _resolve_placeholders
        from src.session.data import SessionData

        session = SessionData()
        session.data_map = {"key": "val"}
        session.long_mem_data = "long mem text"
        session.add_turn("q1", "a1")
        session.add_turn("q2", "a2")

        result = _resolve_placeholders(
            "Context: {{context}}\nHistory:\n{{history}}\n"
            "Query: {{query}}\nData: {{data_map}}\nMem: {{long_mem}}",
            session, "my context", "my query",
        )
        assert "my context" in result
        assert "my query" in result
        assert "q1" in result
        assert "a1" in result
        assert "q2" in result
        assert "a2" in result
        assert "val" in result
        assert "long mem text" in result

    def test_resolve_no_history_placeholder(self):
        from src.engine.tools.llm_tool import _resolve_placeholders
        from src.session.data import SessionData

        session = SessionData()
        result = _resolve_placeholders("{{query}} only", session, "", "hi")
        assert result == "hi only"


class TestRAGSearchEdges:
    def test_reset_qdrant(self):
        import importlib
        m = importlib.import_module("src.engine.tools.rag_search")
        m._qdrant = object()
        m._reset_qdrant()
        assert m._qdrant is None

    def test_embed_reconnect_retry_fail(self, mocker):
        import importlib
        m = importlib.import_module("src.engine.tools.rag_search")

        class _Boom:
            def embed(self, *_a):
                raise ConnectionError("down")
            def close(self):
                pass

        m._embed_client = _Boom()
        mocker.patch("src.llm.client.LLMClient", return_value=_Boom())

        class P:
            base_url = "http://x"
            api_key = ""
            model = "m"

        assert m._embed_with_reconnect(P(), "q", "k") is None

    def test_embed_reconnect_recovers(self, mocker):
        import importlib
        m = importlib.import_module("src.engine.tools.rag_search")

        class _Boom:
            def embed(self, *_a):
                raise ConnectionError("down")
            def close(self):
                pass

        class _Good:
            def embed(self, *_a):
                return [[0.1, 0.2]]

        m._embed_client = _Boom()
        mocker.patch("src.llm.client.LLMClient", return_value=_Good())

        class P:
            base_url = "http://x"
            api_key = ""
            model = "m"

        assert m._embed_with_reconnect(P(), "q", "k") == [[0.1, 0.2]]

    def test_resolve_collections_from_wf(self, temp_config_dir):
        from src.config import load_app_config

        load_app_config(temp_config_dir)
        from src.engine.tools.rag_search import _resolve_collections
        from src.session.data import SessionData

        session = SessionData(_workflow="default")
        result = _resolve_collections({}, session)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_resolve_collections_fallback(self, temp_config_dir):
        from src.config import load_app_config

        load_app_config(temp_config_dir)
        from src.engine.tools.rag_search import _resolve_collections
        from src.session.data import SessionData

        session = SessionData()
        result = _resolve_collections({}, session)
        assert result == ["default"]

    def test_resolve_collections_unknown_wf_fallback(self, temp_config_dir):
        from src.config import load_app_config

        load_app_config(temp_config_dir)
        from src.engine.tools.rag_search import _resolve_collections
        from src.session.data import SessionData

        session = SessionData(_workflow="nonexistent_wf")
        result = _resolve_collections({}, session)
        assert result == ["default"]

    def test_resolve_collections_list_input(self, temp_config_dir):
        from src.engine.tools.rag_search import _resolve_collections
        from src.session.data import SessionData

        result = _resolve_collections(
            {"collection": ["a", "b"]}, SessionData(),
        )
        assert result == ["a", "b"]

    def test_resolve_collections_string_input(self, temp_config_dir):
        from src.engine.tools.rag_search import _resolve_collections
        from src.session.data import SessionData

        result = _resolve_collections(
            {"collection": "single_col"}, SessionData(),
        )
        assert result == ["single_col"]


class TestMiddleware:
    @pytest.mark.asyncio
    async def test_request_id_middleware_from_header(self):
        from src.logger.middleware import RequestIDMiddleware

        mock_request = MagicMock()
        mock_request.headers = {"X-Request-ID": "my-custom-id"}
        mock_request.state = MagicMock()

        mock_response = MagicMock()
        mock_response.headers = {}

        async def call_next(req):
            return mock_response

        middleware = RequestIDMiddleware(MagicMock())
        response = await middleware.dispatch(mock_request, call_next)
        assert response.headers["X-Request-ID"] == "my-custom-id"

    @pytest.mark.asyncio
    async def test_request_id_middleware_generates_id(self):
        from src.logger.middleware import RequestIDMiddleware

        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.state = MagicMock()

        mock_response = MagicMock()
        mock_response.headers = {}

        async def call_next(req):
            return mock_response

        middleware = RequestIDMiddleware(MagicMock())
        response = await middleware.dispatch(mock_request, call_next)
        assert "X-Request-ID" in response.headers
        assert len(response.headers["X-Request-ID"]) == 12

    @pytest.mark.asyncio
    async def test_metrics_middleware(self):
        from src.metrics.prometheus import MetricsMiddleware

        mock_request = MagicMock()
        mock_request.method = "GET"
        mock_request.url = MagicMock()
        mock_request.url.path = "/api/test"

        mock_response = MagicMock()
        mock_response.status_code = 200

        async def call_next(req):
            return mock_response

        middleware = MetricsMiddleware(MagicMock())
        response = await middleware.dispatch(mock_request, call_next)
        assert response.status_code == 200


class TestPrometheusGenerate:
    def test_generate_latest(self):
        from src.metrics.prometheus import generate_latest

        result = generate_latest()
        assert isinstance(result, str)


class TestQdrantExtra:
    def test_scroll_with_filter(self):
        from unittest.mock import MagicMock

        with patch("src.rag.qdrant.QdrantClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.scroll.return_value = ([], None)
            mock_cls.return_value = mock_client

            from src.rag.qdrant import QdrantSearch

            q = QdrantSearch()
            records, offset = q.scroll_with_filter("col", limit=10)
            assert records == []
            assert offset is None
            mock_client.scroll.assert_called_once_with(
                collection_name="col", limit=10, offset=0,
                with_payload=True, scroll_filter=None,
            )

    def test_scroll_with_filter_and_offset(self):
        from unittest.mock import MagicMock

        with patch("src.rag.qdrant.QdrantClient") as mock_cls:
            mock_client = MagicMock()
            fake_record = MagicMock()
            fake_record.id = 1
            fake_record.payload = {"text": "data"}
            mock_client.scroll.return_value = ([fake_record], None)
            mock_cls.return_value = mock_client

            from src.rag.qdrant import QdrantSearch

            q = QdrantSearch()
            records, offset = q.scroll_with_filter(
                "col", limit=5, offset=10, filter={"k": "v"},
            )
            assert len(records) == 1
            assert records[0]["id"] == 1
            mock_client.scroll.assert_called_once()

    def test_count(self):
        from unittest.mock import MagicMock

        with patch("src.rag.qdrant.QdrantClient") as mock_cls:
            mock_client = MagicMock()
            mock_result = MagicMock()
            mock_result.count = 42
            mock_client.count.return_value = mock_result
            mock_cls.return_value = mock_client

            from src.rag.qdrant import QdrantSearch

            q = QdrantSearch()
            result = q.count("col")
            assert result == 42
            mock_client.count.assert_called_once_with(
                collection_name="col", count_filter=None,
            )

    def test_count_with_filter(self):
        from unittest.mock import MagicMock

        with patch("src.rag.qdrant.QdrantClient") as mock_cls:
            mock_client = MagicMock()
            mock_result = MagicMock()
            mock_result.count = 7
            mock_client.count.return_value = mock_result
            mock_cls.return_value = mock_client

            from src.rag.qdrant import QdrantSearch

            q = QdrantSearch()
            result = q.count("col", filter={"status": "active"})
            assert result == 7

    def test_build_filter(self):
        from src.rag.qdrant import _build_filter

        result = _build_filter({"status": "active", "count": {"range": {"gte": 5}}})
        assert result is not None


class TestLoadOptionalFallthrough:
    def test_load_optional_config_unknown_name(self, tmp_path):
        cfg_dir = tmp_path / "cfg"
        cfg_dir.mkdir()
        from src.config import _load_optional_config

        result = _load_optional_config(cfg_dir, "unknown_config")
        assert result is None


class TestWebSearchExtra:
    def test_search_results_at_limit(self, monkeypatch):
        mock_response = MagicMock()
        parts = []
        for i in range(10):
            parts.append(
                '<div class="result">'
                f'<a class="result__a" href="http://example{i}.com">Title {i}</a>'
                f'<a class="result__snippet">Snippet {i}</a>'
                '</div>'
            )
        mock_response.text = "".join(parts)

        def mock_post(url, data=None, headers=None, timeout=None):
            return mock_response

        monkeypatch.setattr("httpx2.post", mock_post)

        from src.engine.tools.web_search import web_search
        from src.session.data import SessionData

        config = {"engine": "duckduckgo", "query_template": "{{query}}", "limit": 3}
        session = SessionData()
        session.nodes = [{"name": "input", "data": {"text": "multi"}}]
        result = web_search(config, session)
        assert len(result["results"]) == 3

    def test_resolve_with_data_map(self):
        from src.engine.tools.web_search import _resolve
        from src.session.data import SessionData

        session = SessionData()
        session.nodes = [{"name": "input", "data": {"text": "hi"}}]
        session.data_map["key"] = "val"
        result = _resolve("{{query}} {{key}}", session)
        assert result == "hi val"


class TestSessionDataExtra:
    def test_keys_method(self):
        from src.session.data import SessionData

        session = SessionData()
        keys = session.keys()
        assert "chat_id" in keys
        assert "history" in keys
        assert "data_map" in keys

    def test_from_dict_with_dict_history(self):
        from src.session.data import SessionData

        data = {
            "chat_id": "chat_123",
            "turn_id": 2,
            "created_at": 1000.0,
            "last_active_at": 2000.0,
            "_workflow": "default",
            "return_mode": "full",
            "history": [
                {
                    "input": "q1", "output": "a1",
                    "input_timestamp": 100.0, "output_timestamp": 200.0,
                },
            ],
            "data_map": {},
            "long_mem_data": "",
            "nodes": [],
        }
        session = SessionData.from_dict(data)
        assert len(session.history) == 1
        assert session.history[0].input == "q1"
        assert session.turn_id == 2

    def test_from_dict_with_content_key(self):
        from src.session.data import SessionData

        data = {
            "chat_id": "chat_456",
            "turn_id": 0,
            "created_at": 1000.0,
            "last_active_at": 2000.0,
            "_workflow": "",
            "return_mode": "full",
            "history": [
                {
                    "content": "q1", "output": "a1",
                    "input_timestamp": 100.0, "output_timestamp": 200.0,
                },
            ],
            "data_map": {},
            "long_mem_data": "",
            "nodes": [],
        }
        session = SessionData.from_dict(data)
        assert session.history[0].input == "q1"

    def test_trim_excess_le_zero(self):
        from src.session.data import SessionData

        session = SessionData()
        session.add_turn("q1", "a1")
        session.add_turn("q2", "a2")
        session.add_turn("q3", "a3")
        session.trim_or_compress(max_turns=2, keep=5)
        assert len(session.history) == 3


class TestMemoryStoreExtra:
    def test_touch_existing_session(self):
        from src.session.data import SessionData
        from src.session.memory import MemorySessionStore

        store = MemorySessionStore(max_age=3600)
        session = SessionData(chat_id="test_touch")
        store.save(session)
        store.touch("test_touch")
        raw = store.get("test_touch")
        assert raw is not None

    def test_cleanup_loop_default_stop_event(self, monkeypatch):
        from src.session.memory import MemorySessionStore

        store = MemorySessionStore(max_age=3600)

        class StopAfterOne:
            def __init__(self):
                self.count = 0

            def wait(self, interval):
                self.count += 1
                return self.count > 1

        monkeypatch.setattr("threading.Event", StopAfterOne)
        store.cleanup_loop(interval=0.01)


class TestDAGWalkBranchDirect:
    def test_walk_branch_direct_one_next(self, temp_config_dir):
        from src.config import load_app_config
        from src.engine.dag import DAGEngine
        from src.engine.tool import ToolRegistry

        app_cfg = load_app_config(temp_config_dir)

        def mock_echo(config, session):
            return {"text": "ok"}

        reg = ToolRegistry()
        reg.register("mock_echo", mock_echo)
        app_cfg.nodes["dflt:a"] = {"tool": "mock_echo"}
        app_cfg.nodes["dflt:b"] = {"tool": "mock_echo"}

        engine = DAGEngine(tools=reg, app_config=app_cfg)
        node_map = {
            "a": {"name": "a", "next_type": "one", "next": "b"},
            "b": {"name": "b", "next_type": "one", "next": ""},
        }
        nodes = engine._walk_branch("a", node_map, "dflt")
        assert len(nodes) >= 1
        assert nodes[0]["name"] == "a"

    def test_walk_branch_direct_string_result(self, temp_config_dir):
        from src.config import load_app_config
        from src.engine.dag import DAGEngine
        from src.engine.tool import ToolRegistry

        app_cfg = load_app_config(temp_config_dir)

        def mock_str(config, session):
            return "branch_b"

        def mock_echo(config, session):
            return {"text": "ok"}

        reg = ToolRegistry()
        reg.register("mock_str", mock_str)
        reg.register("mock_echo", mock_echo)
        app_cfg.nodes["dflt:a"] = {"tool": "mock_str"}
        app_cfg.nodes["dflt:b"] = {"tool": "mock_echo"}

        engine = DAGEngine(tools=reg, app_config=app_cfg)
        node_map = {
            "a": {"name": "a", "next_type": "if-then", "next": ["b"]},
            "b": {"name": "b", "next_type": "one", "next": ""},
        }
        nodes = engine._walk_branch("a", node_map, "dflt")
        assert len(nodes) >= 1

    def test_walk_branch_direct_keyerror(self, temp_config_dir):
        from src.config import load_app_config
        from src.engine.dag import DAGEngine
        from src.engine.tool import ToolRegistry

        app_cfg = load_app_config(temp_config_dir)

        def mock_echo(config, session):
            return {"text": "ok"}

        reg = ToolRegistry()
        reg.register("mock_echo", mock_echo)

        engine = DAGEngine(tools=reg, app_config=app_cfg)
        node_map = {"a": {"name": "a", "next_type": "one", "next": ""}}
        with pytest.raises(KeyError, match="not found"):
            engine._walk_branch("a", node_map, "bad_product")

    def test_walk_branch_direct_valueerror(self, temp_config_dir):
        from src.config import load_app_config
        from src.engine.dag import DAGEngine
        from src.engine.tool import ToolRegistry

        app_cfg = load_app_config(temp_config_dir)
        reg = ToolRegistry()
        app_cfg.nodes["dflt:a"] = {"tool": "unknown_tool"}

        engine = DAGEngine(tools=reg, app_config=app_cfg)
        node_map = {"a": {"name": "a", "next_type": "one", "next": ""}}
        with pytest.raises(ValueError, match="unknown tool"):
            engine._walk_branch("a", node_map, "dflt")

    def test_walk_branch_direct_switch_list(self, temp_config_dir):
        from src.config import load_app_config
        from src.engine.dag import DAGEngine
        from src.engine.tool import ToolRegistry

        app_cfg = load_app_config(temp_config_dir)

        def mock_echo(config, session):
            return {"text": "ok"}

        reg = ToolRegistry()
        reg.register("mock_echo", mock_echo)
        app_cfg.nodes["dflt:a"] = {"tool": "mock_echo"}
        app_cfg.nodes["dflt:b"] = {"tool": "mock_echo"}
        app_cfg.nodes["dflt:c"] = {"tool": "mock_echo"}

        engine = DAGEngine(tools=reg, app_config=app_cfg)
        node_map = {
            "a": {"name": "a", "next_type": "switch", "next": ["b", "c"]},
            "b": {"name": "b", "next_type": "one", "next": ""},
            "c": {"name": "c", "next_type": "one", "next": ""},
        }
        nodes = engine._walk_branch("a", node_map, "dflt")
        node_names = [n["name"] for n in nodes]
        assert "b" in node_names
        assert "c" in node_names
