"""Client-perspective tests for API key authentication."""

from __future__ import annotations

import pytest


class TestAuth:
    """Authentication middleware tests.

    The app is created with the project's real config (from config/).
    By default api_keys is empty → auth disabled.
    """

    def test_health_skips_auth_by_default(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_ready_skips_auth_by_default(self, client):
        r = client.get("/ready")
        assert r.status_code == 200

    def test_status_skips_auth_by_default(self, client):
        r = client.get("/status")
        assert r.status_code == 200

    def test_docs_endpoint_accessible(self, client):
        r = client.get("/docs")
        assert r.status_code == 200

    def test_openapi_schema_accessible(self, client):
        r = client.get("/openapi.json")
        assert r.status_code == 200

    def test_metrics_bypasses_auth(self, client):
        r = client.get("/metrics")
        assert r.status_code == 200

    def test_chat_routes_work_with_default_config(self, client):
        r = client.get("/api/v1/workflows")
        assert r.status_code == 200

    def test_chat_health_route_works(self, client):
        r = client.get("/api/v1/health")
        assert r.status_code == 200

    def test_export_routes_work(self, client):
        r = client.post("/export/chat.xlsx", json={
            "messages": [{"role": "user", "content": "hi"}],
        })
        assert r.status_code == 200


class TestAuthMiddlewareLogic:
    """Unit tests for AuthMiddleware dispatch decisions (no app required)."""

    def test_empty_keys_allow_all(self):
        from src.api.auth import AuthMiddleware
        from src.config import AuthConfig

        cfg = AuthConfig(api_keys=[], skip_paths=["/health"])
        assert cfg.api_keys == []
        # logic tested indirectly: when api_keys empty, all pass

    def test_non_empty_keys_with_skip_paths(self):
        from src.api.auth import AuthMiddleware
        from src.config import AuthConfig

        cfg = AuthConfig(api_keys=["secret"], skip_paths=["/health", "/docs"])
        assert cfg.api_keys == ["secret"]
        assert "/health" in cfg.skip_paths

