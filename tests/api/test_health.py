"""Client-perspective tests for health / ready / status / reload / metrics endpoints."""

from __future__ import annotations

import time


class TestHealth:
    """GET /health — liveness probe."""

    def test_returns_200_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert isinstance(data["timestamp"], float)
        assert "startup_seconds" in data

    def test_timestamp_is_recent(self, client):
        r = client.get("/health")
        now = time.time()
        # timestamp should be within last 60s
        assert abs(r.json()["timestamp"] - now) < 60

    def test_response_is_json_with_charset(self, client):
        r = client.get("/health")
        ct = r.headers.get("content-type", "")
        assert "application/json" in ct
        assert "charset=utf-8" in ct


class TestReady:
    """GET /ready — readiness probe."""

    def test_returns_200(self, client):
        r = client.get("/ready")
        assert r.status_code == 200

    def test_status_is_ready(self, client):
        r = client.get("/ready")
        data = r.json()
        assert data["status"] == "ready"

    def test_includes_workflow_list(self, client):
        r = client.get("/ready")
        data = r.json()
        assert isinstance(data["workflows"], list)
        assert len(data["workflows"]) > 0

    def test_includes_probes(self, client):
        r = client.get("/ready")
        data = r.json()
        assert "probes" in data
        probes = data["probes"]
        assert "qdrant" in probes
        assert "embedding" in probes

    def test_includes_llm_embed_defaults(self, client):
        r = client.get("/ready")
        data = r.json()
        assert "llm_default" in data
        assert "embed_default" in data

    def test_v1_health_also_works(self, client):
        r = client.get("/api/v1/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


class TestStatus:
    """GET /status — detailed component status."""

    def test_returns_200(self, client):
        r = client.get("/status")
        assert r.status_code == 200

    def test_status_is_ok_or_degraded(self, client):
        r = client.get("/status")
        assert r.json()["status"] in ("ok", "degraded")

    def test_includes_timestamp(self, client):
        r = client.get("/status")
        assert isinstance(r.json()["timestamp"], float)

    def test_includes_all_component_slots(self, client):
        r = client.get("/status")
        components = r.json()["components"]
        assert "qdrant" in components
        assert "llm" in components
        assert "embedding" in components
        assert "metrics_store" in components

    def test_component_probe_structure(self, client):
        r = client.get("/status")
        for comp_key, comp_val in r.json()["components"].items():
            assert "status" in comp_val
            assert "latency_ms" in comp_val
            assert "detail" in comp_val
            assert comp_val["status"] in ("ok", "error")

    def test_process_info(self, client):
        r = client.get("/status")
        proc = r.json()["process"]
        assert "version" in proc
        assert proc["version"]
        assert "python" in proc
        assert "uptime_seconds" in proc
        assert isinstance(proc["uptime_seconds"], (int, float))
        assert "workflow_count" in proc
        assert isinstance(proc["workflow_count"], int)
        assert "workflows" in proc
        assert isinstance(proc["workflows"], list)


class TestMetrics:
    """GET /metrics — Prometheus metrics endpoint."""

    def test_returns_200(self, client):
        r = client.get("/metrics")
        assert r.status_code == 200

    def test_returns_plain_text(self, client):
        r = client.get("/metrics")
        assert "text/plain" in r.headers["content-type"]

    def test_contains_standard_metrics(self, client):
        r = client.get("/metrics")
        body = r.text
        assert "python_info" in body or "http" in body.lower()


class TestReload:
    """POST /reload — config reload endpoint."""

    def test_returns_200(self, client):
        r = client.post("/reload")
        assert r.status_code == 200

    def test_returns_ok_status(self, client):
        r = client.post("/reload")
        data = r.json()
        assert data["status"] == "ok"
        assert "workflows" in data
        assert isinstance(data["workflows"], list)

    def test_get_is_not_allowed(self, client):
        r = client.get("/reload")
        assert r.status_code == 405


class TestPrometheusMetrics:
    """GET /metrics — additional assertions."""

    def test_response_not_empty(self, client):
        r = client.get("/metrics")
        assert len(r.text) > 0

    def test_cors_headers_present_with_origin(self, client):
        r = client.get("/metrics", headers={"Origin": "http://localhost:5173"})
        # CORS middleware should allow the origin
        assert r.headers.get("access-control-allow-origin") == "*"
