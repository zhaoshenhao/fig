from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

_proj_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_proj_root))


def _reset_service_state():
    """重置 service 模块的单例全局，隔离用例间状态。"""
    from src.embed_service import service

    service._model = None
    service._model_name = None


class TestEmbedServiceModule:
    def test_resolve_model_name_aliases(self):
        from src.embed_service import service

        nomic = "nomic-ai/nomic-embed-text-v1.5"
        assert service.resolve_model_name("nomic-embed-text") == nomic
        assert service.resolve_model_name("nomic-embed-text-v1.5") == nomic
        assert service.resolve_model_name("") == service.DEFAULT_MODEL

    def test_resolve_model_name_passthrough(self):
        from src.embed_service import service

        assert service.resolve_model_name("custom/model") == "custom/model"

    def test_is_ready_false_initially(self):
        from src.embed_service import service

        _reset_service_state()
        assert service.is_ready() is False

    def test_get_model_caches_single_load(self, mocker):
        from src.embed_service import service

        _reset_service_state()
        fake = object()
        load = mocker.patch.object(service, "_load_model", return_value=fake)

        m1 = service.get_model("nomic-embed-text")
        m2 = service.get_model("nomic-embed-text")

        assert m1 is fake and m2 is fake
        load.assert_called_once_with("nomic-ai/nomic-embed-text-v1.5")
        assert service.is_ready() is True

    def test_get_model_reloads_on_name_change(self, mocker):
        from src.embed_service import service

        _reset_service_state()
        load = mocker.patch.object(service, "_load_model", side_effect=[object(), object()])

        service.get_model("nomic-embed-text")
        service.get_model("BAAI/bge-small-en-v1.5")

        assert load.call_count == 2

    def test_embed_texts_converts_floats(self, mocker):
        from src.embed_service import service

        class _FakeModel:
            def embed(self, texts):
                for _ in texts:
                    yield [0, 1, 2]  # ints -> 应转为 float

        mocker.patch.object(service, "get_model", return_value=_FakeModel())
        vectors = service.embed_texts(["a", "b"], "nomic-embed-text")

        assert len(vectors) == 2
        assert vectors[0] == [0.0, 1.0, 2.0]
        assert all(isinstance(x, float) for x in vectors[0])


class TestEmbedServiceAPI:
    @staticmethod
    def _client():
        from src.embed_service.app import app

        # 不使用 with-上下文 => 不触发 lifespan 预热（避免真实加载模型）
        return TestClient(app, raise_server_exceptions=False)

    def test_health(self):
        r = self._client().get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_ready_503_when_model_not_loaded(self, mocker):
        mocker.patch("src.embed_service.app.is_ready", return_value=False)
        r = self._client().get("/ready")
        assert r.status_code == 503

    def test_ready_200_when_model_loaded(self, mocker):
        mocker.patch("src.embed_service.app.is_ready", return_value=True)
        r = self._client().get("/ready")
        assert r.status_code == 200
        assert r.json()["status"] == "ready"

    def test_embeddings_single_string(self, mocker):
        mocker.patch("src.embed_service.app.embed_texts", return_value=[[0.1, 0.2, 0.3]])
        payload = {"model": "nomic-embed-text", "input": "hello"}
        r = self._client().post("/v1/embeddings", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data["object"] == "list"
        assert len(data["data"]) == 1
        assert data["data"][0]["embedding"] == [0.1, 0.2, 0.3]
        assert data["data"][0]["index"] == 0
        assert data["model"] == "nomic-embed-text"
        assert "usage" in data

    def test_embeddings_list_of_strings(self, mocker):
        spy = mocker.patch(
            "src.embed_service.app.embed_texts",
            return_value=[[0.1, 0.2], [0.3, 0.4]],
        )
        r = self._client().post("/v1/embeddings", json={"input": ["a", "b"]})
        assert r.status_code == 200
        data = r.json()
        assert len(data["data"]) == 2
        assert data["data"][1]["index"] == 1
        # input 为列表时应原样传入
        assert spy.call_args[0][0] == ["a", "b"]

    def test_embeddings_empty_list_returns_400(self):
        r = self._client().post("/v1/embeddings", json={"input": []})
        assert r.status_code == 400

    def test_embeddings_missing_input_returns_422(self):
        r = self._client().post("/v1/embeddings", json={"model": "x"})
        assert r.status_code == 422

    def test_embeddings_default_model_from_env(self, mocker, monkeypatch):
        monkeypatch.setenv("EMBED_MODEL", "custom-default")
        spy = mocker.patch("src.embed_service.app.embed_texts", return_value=[[1.0]])
        r = self._client().post("/v1/embeddings", json={"input": "hi"})
        assert r.status_code == 200
        assert r.json()["model"] == "custom-default"
        # 未指定 model 时应使用环境变量默认值
        assert spy.call_args[0][1] == "custom-default"


class TestEmbedServiceAuth:
    @staticmethod
    def _client():
        from src.embed_service.app import app

        return TestClient(app, raise_server_exceptions=False)

    def test_no_key_disables_auth(self, mocker, monkeypatch):
        monkeypatch.delenv("EMBED_API_KEY", raising=False)
        mocker.patch("src.embed_service.app.embed_texts", return_value=[[1.0]])
        r = self._client().post("/v1/embeddings", json={"input": "hi"})
        assert r.status_code == 200

    def test_missing_key_rejected(self, monkeypatch):
        monkeypatch.setenv("EMBED_API_KEY", "secret-123")
        r = self._client().post("/v1/embeddings", json={"input": "hi"})
        assert r.status_code == 401

    def test_wrong_key_rejected(self, monkeypatch):
        monkeypatch.setenv("EMBED_API_KEY", "secret-123")
        r = self._client().post(
            "/v1/embeddings", json={"input": "hi"}, headers={"X-API-Key": "nope"}
        )
        assert r.status_code == 401

    def test_valid_x_api_key(self, mocker, monkeypatch):
        monkeypatch.setenv("EMBED_API_KEY", "secret-123")
        mocker.patch("src.embed_service.app.embed_texts", return_value=[[1.0]])
        r = self._client().post(
            "/v1/embeddings", json={"input": "hi"}, headers={"X-API-Key": "secret-123"}
        )
        assert r.status_code == 200

    def test_valid_bearer_token(self, mocker, monkeypatch):
        monkeypatch.setenv("EMBED_API_KEY", "secret-123")
        mocker.patch("src.embed_service.app.embed_texts", return_value=[[1.0]])
        r = self._client().post(
            "/v1/embeddings",
            json={"input": "hi"},
            headers={"Authorization": "Bearer secret-123"},
        )
        assert r.status_code == 200

    def test_probes_skip_auth(self, monkeypatch, mocker):
        monkeypatch.setenv("EMBED_API_KEY", "secret-123")
        mocker.patch("src.embed_service.app.is_ready", return_value=True)
        c = self._client()
        assert c.get("/health").status_code == 200
        assert c.get("/ready").status_code == 200
