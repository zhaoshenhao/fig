from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_proj_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_proj_root))


class TestLoadAppConfig:
    def test_loads_all_configs_from_dir(self, temp_config_dir):
        from src.config import load_app_config

        cfg = load_app_config(temp_config_dir, env_file=".env")

        assert cfg is not None
        assert len(cfg.workflows) == 6
        assert "default" in cfg.workflows
        assert "switch_wf" in cfg.workflows
        assert isinstance(cfg.llm_provider(), object)
        assert isinstance(cfg.embed_provider(), object)

    def test_singleton_get_app_config(self, temp_config_dir):
        import src.config as cfg_mod

        result = cfg_mod.load_app_config(temp_config_dir, env_file=".env")
        stored = cfg_mod.get_app_config()

        assert stored is cfg_mod._APP_CONFIG
        assert stored is result
        assert stored is not None

    def test_get_app_config_before_load_raises(self, monkeypatch):
        from src.config import _APP_CONFIG, get_app_config

        saved = _APP_CONFIG
        import src.config as mod

        monkeypatch.setattr(mod, "_APP_CONFIG", None)
        with pytest.raises(RuntimeError, match="not loaded"):
            get_app_config()
        monkeypatch.setattr(mod, "_APP_CONFIG", saved)

    def test_llm_config_not_loaded_raises(self, temp_config_dir):
        from src.config import load_app_config

        cfg = load_app_config(temp_config_dir)
        cfg.llm = None
        with pytest.raises(RuntimeError, match="llm config not loaded"):
            cfg.llm_provider()

    def test_embed_config_not_loaded_raises(self, temp_config_dir):
        from src.config import load_app_config

        cfg = load_app_config(temp_config_dir)
        cfg.embed = None
        with pytest.raises(RuntimeError, match="embed config not loaded"):
            cfg.embed_provider()

    def test_node_config_not_found_raises(self, temp_config_dir):
        from src.config import load_app_config

        cfg = load_app_config(temp_config_dir)
        with pytest.raises(KeyError, match="nonexistent"):
            cfg.node_config("nonexistent")

    def test_llm_provider_default(self, temp_config_dir):
        from src.config import load_app_config

        cfg = load_app_config(temp_config_dir)
        p = cfg.llm_provider()
        assert p.model == "test-model"
        assert p.type == "openai"

    def test_llm_provider_by_name(self, temp_config_dir):
        from src.config import load_app_config

        cfg = load_app_config(temp_config_dir)
        p = cfg.llm_provider("test_llm")
        assert p.base_url == "https://test.example.com/v1"

    def test_llm_provider_not_found(self, temp_config_dir):
        from src.config import load_app_config

        cfg = load_app_config(temp_config_dir)
        with pytest.raises(KeyError, match="not found"):
            cfg.llm_provider("bad_provider")

    def test_embed_provider_default(self, temp_config_dir):
        from src.config import load_app_config

        cfg = load_app_config(temp_config_dir)
        p = cfg.embed_provider()
        assert p.model == "text-embed-3-small"
        assert p.dims == 768

    def test_embed_provider_not_found(self, temp_config_dir):
        from src.config import load_app_config

        cfg = load_app_config(temp_config_dir)
        with pytest.raises(KeyError, match="not found"):
            cfg.embed_provider("bad_provider")


class TestEnvResolve:
    def test_resolves_env_vars_in_config(self, tmp_path: Path):
        cfg = tmp_path / "config"
        wf_dir = cfg / "workflows"
        wf_dir.mkdir(parents=True)

        os.environ["TEST_KEY_FOO"] = "bar_value"

        (cfg / "llm.yaml").write_text(
            """default: ollama
providers:
  ollama:
    type: openai
    base_url: http://localhost:11434/v1
    api_key: ${TEST_KEY_FOO}
    model: test""",
            encoding="utf-8",
        )
        (cfg / "embed.yaml").write_text(
            "default: ollama\nproviders: {}", encoding="utf-8"
        )
        (cfg / "workflow.yaml").write_text(
            "workflows: []", encoding="utf-8"
        )

        from src.config import load_app_config

        cfg_obj = load_app_config(cfg)
        p = cfg_obj.llm_provider("ollama")
        assert p.api_key == "bar_value"

    def test_missing_env_var_becomes_empty(self, tmp_path: Path):
        cfg = tmp_path / "config"
        wf_dir = cfg / "workflows"
        wf_dir.mkdir(parents=True)

        (cfg / "llm.yaml").write_text(
            """default: ollama
providers:
  ollama:
    type: openai
    base_url: http://localhost:11434/v1
    api_key: ${NONEXISTENT_VAR}
    model: test""",
            encoding="utf-8",
        )
        (cfg / "embed.yaml").write_text(
            "default: ollama\nproviders: {}", encoding="utf-8"
        )
        (cfg / "workflow.yaml").write_text(
            "workflows: []", encoding="utf-8"
        )

        from src.config import load_app_config

        cfg_obj = load_app_config(cfg)
        p = cfg_obj.llm_provider("ollama")
        assert p.api_key == ""


class TestGetWorkflow:
    def test_returns_workflow_by_name(self, temp_config_dir):
        from src.config import get_workflow

        wf = get_workflow(temp_config_dir, "default")
        assert wf["name"] == "default"

    def test_raises_for_unknown_workflow(self, temp_config_dir):
        from src.config import get_workflow

        with pytest.raises(KeyError, match="not found"):
            get_workflow(temp_config_dir, "nonexistent")


class TestLLMProvider:
    def test_fields(self):
        from src.config import LLMProvider

        p = LLMProvider(
            type="openai",
            base_url="https://api.example.com/v1",
            api_key="k",
            model="m",
        )
        assert p.type == "openai"
        assert p.base_url == "https://api.example.com/v1"
        assert p.api_key == "k"
        assert p.model == "m"


class TestEmbedProvider:
    def test_fields(self):
        from src.config import EmbedProvider

        p = EmbedProvider(
            type="openai",
            base_url="https://api.example.com/v1",
            api_key="k",
            model="m",
            dims=768,
        )
        assert p.type == "openai"
        assert p.dims == 768
