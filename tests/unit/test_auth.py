from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

_proj_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_proj_root))


def _make_app(config):
    from src.api.auth import AuthMiddleware
    from src.config import AuthConfig

    cfg = AuthConfig(**config) if isinstance(config, dict) else config

    app = FastAPI()

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/ready")
    async def ready():
        return {"status": "ready"}

    @app.get("/workflows/default")
    async def workflow():
        return {"name": "default"}

    @app.get("/docs")
    async def docs():
        return {"docs": True}

    app.add_middleware(AuthMiddleware, config=cfg)
    return TestClient(app, raise_server_exceptions=False)


class TestAuthMiddleware:
    def test_no_keys_allows_all(self):
        client = _make_app({"api_keys": [], "skip_paths": []})

        r = client.get("/workflows/default")
        assert r.status_code == 200

        r = client.get("/health")
        assert r.status_code == 200

    def test_missing_key_returns_401(self):
        client = _make_app({"api_keys": ["secret"], "skip_paths": []})

        r = client.get("/workflows/default")
        assert r.status_code == 401
        assert "X-API-Key" in r.json()["error"]

    def test_invalid_key_returns_401(self):
        client = _make_app({"api_keys": ["secret"], "skip_paths": []})

        r = client.get("/workflows/default", headers={"X-API-Key": "wrong"})
        assert r.status_code == 401

    def test_valid_key_passes(self):
        client = _make_app({"api_keys": ["secret", "key2"], "skip_paths": []})

        r = client.get("/workflows/default", headers={"X-API-Key": "secret"})
        assert r.status_code == 200

        r = client.get("/workflows/default", headers={"X-API-Key": "key2"})
        assert r.status_code == 200

    def test_skip_paths_bypass_auth(self):
        client = _make_app({
            "api_keys": ["secret"],
            "skip_paths": ["/health", "/ready"],
        })

        r = client.get("/health")
        assert r.status_code == 200

        r = client.get("/ready")
        assert r.status_code == 200

        r = client.get("/workflows/default")
        assert r.status_code == 401

    def test_skip_docs_openapi(self):
        client = _make_app({
            "api_keys": ["secret"],
            "skip_paths": ["/docs", "/openapi.json"],
        })

        r = client.get("/docs")
        assert r.status_code == 200

        r = client.get("/openapi.json")
        assert r.status_code == 200


class TestAuthConfig:
    def test_loads_empty_keys(self):
        from src.config import AuthConfig

        cfg = AuthConfig()
        assert cfg.api_keys == []
        assert cfg.skip_paths == []
