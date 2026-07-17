"""Client-perspective tests for mode-based route availability (KF_MODE).

These tests verify that with the current KF_MODE setting, the expected
routes are accessible and return correct status codes.
"""

from __future__ import annotations


class TestRouteAvailability:
    """Verify all expected routes are reachable with the current mode."""

    def test_chat_workflow_list(self, client):
        r = client.get("/api/v1/workflows")
        assert r.status_code == 200

    def test_chat_workflow_get(self, client):
        r = client.get("/api/v1/workflows/default")
        assert r.status_code == 200

    def test_chat_session_delete_nonexistent(self, client):
        r = client.delete("/api/v1/sessions/chat_nonexistent_xyz")
        assert r.status_code == 404

    def test_chat_feedback_get(self, client):
        r = client.get("/api/v1/sessions/chat_test/turns/0/feedback")
        assert r.status_code == 200

    def test_chat_usage(self, client):
        r = client.get("/api/v1/usage")
        assert r.status_code == 200

    def test_admin_metrics_summary(self, client):
        r = client.get("/metrics/summary")
        assert r.status_code == 200

    def test_admin_metrics_timeseries(self, client):
        r = client.get("/metrics/timeseries", params={"workflow": "default"})
        assert r.status_code == 200

    def test_admin_export_training(self, client):
        r = client.get("/export/training.jsonl", params={"limit": 1})
        assert r.status_code == 200

    def test_export_chat_xlsx(self, client):
        r = client.post("/export/chat.xlsx", json={
            "messages": [{"role": "user", "content": "hi"}],
        })
        assert r.status_code == 200

    def test_export_chat_csv(self, client):
        r = client.post("/export/chat.csv", json={
            "messages": [{"role": "assistant", "content": "hi"}],
        })
        assert r.status_code == 200


class TestRouteMethods:
    """Verify correct HTTP method enforcement."""

    def test_reload_rejects_get(self, client):
        r = client.get("/reload")
        assert r.status_code == 405

    def test_health_rejects_post(self, client):
        r = client.post("/health")
        assert r.status_code == 405

    def test_ready_rejects_post(self, client):
        r = client.post("/ready")
        assert r.status_code == 405


class TestNotFound:
    """Verify 404 for nonexistent routes."""

    def test_unknown_route_returns_404(self, client):
        r = client.get("/nonexistent/path/xyz")
        assert r.status_code == 404

    def test_unknown_workflow_returns_404(self, client):
        r = client.get("/api/v1/workflows/nonexistent_wf_999")
        assert r.status_code == 404
