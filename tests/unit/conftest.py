from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

_proj_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_proj_root))

# Pre-load mocks for optional dependencies not installed in test env.
_opt_deps = {
    "httpx2": MagicMock(),
    "qdrant_client": MagicMock(),
    "qdrant_client.models": MagicMock(),
    "pymysql": MagicMock(),
    "psycopg2": MagicMock(),
}
for _name, _mock in _opt_deps.items():
    sys.modules[_name] = _mock


@pytest.fixture
def temp_config_dir(tmp_path: Path) -> Path:
    cfg = tmp_path / "config"
    cfg.mkdir(parents=True)
    wp = cfg / "workflows"

    (cfg / "llm.yaml").write_text(
        yaml.dump(
            {
                "default": "test_llm",
                "providers": {
                    "test_llm": {
                        "type": "openai",
                        "base_url": "https://test.example.com/v1",
                        "api_key": "test-key-123",
                        "model": "test-model",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    (cfg / "embed.yaml").write_text(
        yaml.dump(
            {
                "default": "test_embed",
                "providers": {
                    "test_embed": {
                        "type": "openai",
                        "base_url": "https://test.example.com/v1",
                        "api_key": "test-key-456",
                        "model": "text-embed-3-small",
                        "dims": 768,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    _make_product(wp, "default", [
        {"name": "retrieve", "next_type": "one", "next": "generate"},
        {"name": "generate", "next_type": "one", "next": ""},
    ])

    _make_product(wp, "if_then_wf", [
        {"name": "router_a", "next_type": "if-then", "next": ["greet", "farewell"]},
        {"name": "greet", "next_type": "one", "next": ""},
        {"name": "farewell", "next_type": "one", "next": ""},
    ])

    _make_product(wp, "switch_wf", [
        {"name": "dispatcher", "next_type": "switch",
         "next": ["branch_a", "branch_b"], "parallel": False},
        {"name": "branch_a", "next_type": "one", "next": ""},
        {"name": "branch_b", "next_type": "one", "next": ""},
    ])

    _make_product(wp, "switch_parallel_wf", [
        {"name": "dispatcher", "next_type": "switch",
         "next": ["branch_x", "branch_y"], "parallel": True},
        {"name": "branch_x", "next_type": "one", "next": ""},
        {"name": "branch_y", "next_type": "one", "next": ""},
    ])

    _make_product(wp, "last_mode_wf", [
        {"name": "echo", "next_type": "one", "next": ""},
    ], return_mode="last")

    _make_product(wp, "metrics_wf", [
        {"name": "step", "next_type": "one", "next": "", "metrics": True},
    ])

    _node_configs: dict[str, dict[str, dict]] = {
        "default": {
            "retrieve": {"tool": "mock_search", "llm_provider": "test_llm"},
            "generate": {
                "tool": "mock_llm",
                "llm_provider": "test_llm",
                "system_prompt": "You are helpful.",
            },
        },
        "if_then_wf": {
            "router_a": {
                "tool": "router",
                "router": {
                    "rules": [{"value": "hello", "match": "contains", "branch": "greet"}],
                    "default": "farewell",
                },
            },
            "greet": {"tool": "mock_echo", "message": "hello"},
            "farewell": {"tool": "mock_echo", "message": "goodbye"},
        },
        "switch_wf": {
            "dispatcher": {"tool": "mock_switch"},
            "branch_a": {"tool": "mock_echo", "message": "A"},
            "branch_b": {"tool": "mock_echo", "message": "B"},
        },
        "switch_parallel_wf": {
            "dispatcher": {"tool": "mock_switch"},
            "branch_x": {"tool": "mock_echo", "message": "X"},
            "branch_y": {"tool": "mock_echo", "message": "Y"},
        },
        "last_mode_wf": {
            "echo": {"tool": "mock_echo", "message": "echo"},
        },
        "metrics_wf": {
            "step": {"tool": "mock_echo", "message": "metrics_test"},
        },
    }

    for product, nodes in _node_configs.items():
        nd = wp / product / "nodes"
        for name, cfg_data in nodes.items():
            (nd / f"{name}.yaml").write_text(
                yaml.dump(cfg_data, allow_unicode=True),
                encoding="utf-8",
            )

    return cfg


def _make_product(
    wp: Path,
    name: str,
    nodes: list[dict],
    return_mode: str = "full",
) -> None:
    product_dir = wp / name
    nodes_dir = product_dir / "nodes"
    nodes_dir.mkdir(parents=True)

    wf_data = {
        "name": name,
        "description": f"workflow {name}",
        "collections": ["default"],
        "return_mode": return_mode,
        "nodes": nodes,
    }
    (product_dir / "workflow.yaml").write_text(
        yaml.dump(wf_data, allow_unicode=True),
        encoding="utf-8",
    )


@pytest.fixture
def mock_tools():
    from src.engine.tool import ToolRegistry

    registry = ToolRegistry()

    def mock_search(_config, session):
        return {"text": "search result text", "chunks": ["doc1", "doc2"], "results": []}

    def mock_llm(_config, session):
        return {"text": "generated response", "model": "test-model"}

    def mock_echo(config, _session):
        return {"text": config.get("message", "default")}

    def mock_switch(_config, session):
        return {"text": "switch triggered"}

    from src.engine.tools.router import router as _router

    registry.register("mock_search", mock_search)
    registry.register("mock_llm", mock_llm)
    registry.register("mock_echo", mock_echo)
    registry.register("mock_switch", mock_switch)
    registry.register("router", _router)

    return registry
