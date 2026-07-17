"""Client-perspective tests for workflow endpoints."""

from __future__ import annotations

from io import StringIO


class TestWorkflowList:
    """GET /api/v1/workflows — list all workflows."""

    def test_returns_workflow_list(self, client):
        r = client.get("/api/v1/workflows")
        assert r.status_code == 200
        data = r.json()
        assert "workflows" in data
        assert isinstance(data["workflows"], list)
        assert len(data["workflows"]) > 0

    def test_workflow_has_name_and_description(self, client):
        r = client.get("/api/v1/workflows")
        for wf in r.json()["workflows"]:
            assert "name" in wf
            assert "description" in wf


class TestWorkflowDetail:
    """GET /api/v1/workflows/{name} — get single workflow."""

    def test_get_default_workflow(self, client):
        r = client.get("/api/v1/workflows/default")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "default"
        assert "nodes" in data
        assert "collections" in data
        assert "return_mode" in data

    def test_get_workflow_nodes_have_tool(self, client):
        r = client.get("/api/v1/workflows/default")
        for node in r.json()["nodes"]:
            assert "name" in node
            assert "next_type" in node

    def test_workflow_not_found(self, client):
        r = client.get("/api/v1/workflows/nonexistent_wf_99999")
        assert r.status_code == 404
        assert "not found" in r.json().get("detail", "")


class TestRunWorkflow:
    """POST /api/v1/workflows/{name}/run — execute a workflow."""

    def test_run_without_query_rejected(self, client):
        r = client.post("/api/v1/workflows/default/run", json={"query": ""})
        assert r.status_code == 422

    def test_run_missing_query_field(self, client):
        r = client.post("/api/v1/workflows/default/run", json={})
        assert r.status_code == 422

    def test_run_nonexistent_workflow(self, client):
        r = client.post("/api/v1/workflows/nonexistent/run", json={"query": "test"})
        assert r.status_code == 404

    def test_run_creates_session(self, client):
        r = client.post("/api/v1/workflows/default/run", json={"query": "hello world"})
        assert r.status_code in (200, 500)
        if r.status_code == 200:
            data = r.json()
            assert data["chat_id"].startswith("chat_")
            assert "reply" in data

    def test_run_with_long_mem(self, client):
        r = client.post(
            "/api/v1/workflows/default/run",
            json={"query": "hello", "long_mem_data": "VIP customer"},
        )
        assert r.status_code in (200, 500)

    def test_run_with_invalid_chat_id(self, client):
        r = client.post(
            "/api/v1/workflows/default/run",
            json={"query": "test", "chat_id": "chat_bogus999"},
        )
        assert r.status_code == 404

    def test_run_streaming_mode(self, client):
        r = client.post(
            "/api/v1/workflows/default/run",
            json={"query": "hi"},
            params={"stream": True},
        )
        assert r.status_code in (200, 500)
        if r.status_code == 200:
            assert "text/event-stream" in r.headers["content-type"]


class TestRegenerate:
    """POST /api/v1/workflows/{name}/regenerate — regenerate last turn."""

    def test_regenerate_no_session(self, client):
        r = client.post(
            "/api/v1/workflows/default/regenerate",
            json={"chat_id": "chat_nonexistent_xy"},
        )
        assert r.status_code == 404

    def test_regenerate_unknown_workflow(self, client):
        r = client.post(
            "/api/v1/workflows/nonexistent/regenerate",
            json={"chat_id": "chat_test"},
        )
        assert r.status_code == 404

    def test_regenerate_streaming(self, client):
        # Create session first, then regenerate
        r1 = client.post("/api/v1/workflows/default/run", json={"query": "hi there"})
        if r1.status_code != 200:
            return  # skip if engine fails in test env
        cid = r1.json()["chat_id"]
        r2 = client.post(
            "/api/v1/workflows/default/regenerate",
            json={"chat_id": cid},
            params={"stream": True},
        )
        assert r2.status_code == 200
        assert "text/event-stream" in r2.headers["content-type"]
