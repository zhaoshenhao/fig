"""Client-perspective tests for RAG metrics, usage, and misc endpoints."""

from __future__ import annotations


class TestUsage:
    """GET /api/v1/usage — aggregate usage stats."""

    def test_usage_returns_tokens(self, client):
        r = client.get("/api/v1/usage")
        assert r.status_code == 200
        data = r.json()
        assert "total_runs" in data
        assert "total_sessions" in data
        assert "prompt_tokens" in data
        assert "completion_tokens" in data
        assert "total_tokens" in data
        assert "error_rate" in data

    def test_usage_with_time_range(self, client):
        r = client.get("/api/v1/usage",
                        params={"time_from": "2025-01-01", "time_to": "2026-01-01"})
        assert r.status_code == 200


class TestRAGSummary:
    """GET /metrics/rag — RAG retrieval summary."""

    def test_rag_summary(self, client):
        r = client.get("/metrics/rag")
        assert r.status_code == 200

    def test_rag_summary_with_workflow(self, client):
        r = client.get("/metrics/rag", params={"workflow": "default"})
        assert r.status_code == 200

    def test_rag_summary_with_time_range(self, client):
        r = client.get("/metrics/rag",
                        params={"time_from": "2025-01-01", "time_to": "2026-01-01"})
        assert r.status_code == 200


class TestMetricsFeedback:
    """GET /metrics/feedback — aggregated feedback listing."""

    def test_feedback_list(self, client):
        r = client.get("/metrics/feedback", params={"limit": 10})
        assert r.status_code == 200
        data = r.json()
        assert "feedback" in data
        assert "count" in data

    def test_feedback_filter_by_rating(self, client):
        r = client.get("/metrics/feedback", params={"rating": "up", "limit": 5})
        assert r.status_code == 200

    def test_feedback_filter_by_workflow(self, client):
        r = client.get("/metrics/feedback",
                        params={"workflow": "default", "limit": 5})
        assert r.status_code == 200


class TestMetricsRetention:
    """POST /metrics/retention — purge old data."""

    def test_retention_requires_days(self, client):
        r = client.post("/metrics/retention")
        assert r.status_code == 422

    def test_retention_very_old_cutoff(self, client):
        r = client.post("/metrics/retention", params={"days": 36500})
        assert r.status_code == 200
        assert r.json()["deleted_runs"] == 0


class TestOpenAPI:
    """Verify OpenAPI schema and docs."""

    def test_schema_has_paths(self, client):
        r = client.get("/openapi.json")
        assert r.status_code == 200
        data = r.json()
        assert "paths" in data
        assert "/health" in data["paths"]

    def test_docs_ui(self, client):
        r = client.get("/docs")
        assert r.status_code == 200
