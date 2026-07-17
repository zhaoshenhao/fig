"""Client-perspective tests for session management endpoints."""

from __future__ import annotations


class TestSessionDelete:
    """DELETE /api/v1/sessions/{chat_id} — delete a session."""

    def test_delete_nonexistent_session(self, client):
        r = client.delete("/api/v1/sessions/chat_nonexistent_xyz")
        assert r.status_code == 404

    def test_delete_returns_204_on_success(self, client):
        # Create a session first
        r1 = client.post("/api/v1/workflows/default/run", json={"query": "to delete"})
        if r1.status_code != 200:
            return
        cid = r1.json()["chat_id"]
        r2 = client.delete(f"/api/v1/sessions/{cid}")
        assert r2.status_code == 204
        # Session should be gone
        r3 = client.post(
            "/api/v1/workflows/default/run",
            json={"query": "check", "chat_id": cid},
        )
        assert r3.status_code == 404


class TestSessionMeta:
    """GET/PATCH /api/v1/sessions/{chat_id}/meta — session metadata."""

    def test_get_meta_unknown_session(self, client):
        r = client.get("/api/v1/sessions/nope_meta_test/meta")
        assert r.status_code == 200
        data = r.json()
        assert data["chat_id"] == "nope_meta_test"
        assert data["title"] == ""

    def test_patch_title_and_tags(self, client):
        r = client.patch(
            "/api/v1/sessions/meta_abc/meta",
            json={"title": "test session", "tags": ["tag1", "tag2"]},
        )
        assert r.status_code == 200
        assert r.json()["title"] == "test session"
        assert r.json()["tags"] == ["tag1", "tag2"]

    def test_patch_title_only(self, client):
        r = client.patch(
            "/api/v1/sessions/meta_title/meta",
            json={"title": "just title"},
        )
        assert r.status_code == 200
        assert r.json()["title"] == "just title"

    def test_patch_tags_only(self, client):
        r = client.patch(
            "/api/v1/sessions/meta_tags/meta",
            json={"tags": ["a"]},
        )
        assert r.status_code == 200
        assert r.json()["tags"] == ["a"]

    def test_patch_persists(self, client):
        cid = "meta_persist"
        client.patch(f"/api/v1/sessions/{cid}/meta", json={"title": "persisted"})
        r = client.get(f"/api/v1/sessions/{cid}/meta")
        assert r.json()["title"] == "persisted"


class TestSessionFilters:
    """GET /api/v1/sessions/filters — filter facets."""

    def test_facets_structure(self, client):
        r = client.get("/api/v1/sessions/filters")
        assert r.status_code == 200
        data = r.json()
        assert "workflows" in data
        assert "nodes" in data
        assert "tools" in data
        assert isinstance(data["workflows"], list)
        assert isinstance(data["nodes"], list)
        assert isinstance(data["tools"], list)


class TestSessionListing:
    """GET /api/v1/sessions — admin session search."""

    def test_list_no_filter(self, client):
        r = client.get("/api/v1/sessions")
        assert r.status_code == 200
        data = r.json()
        assert "sessions" in data
        assert "total" in data

    def test_list_with_workflow_filter(self, client):
        r = client.get("/api/v1/sessions", params={"workflow": "default"})
        assert r.status_code == 200

    def test_list_with_node_filter(self, client):
        r = client.get("/api/v1/sessions", params={"node": "generate"})
        assert r.status_code == 200

    def test_list_with_tool_filter(self, client):
        r = client.get("/api/v1/sessions", params={"tool": "llm"})
        assert r.status_code == 200

    def test_list_with_text_filter(self, client):
        r = client.get("/api/v1/sessions", params={"output_text": "test"})
        assert r.status_code == 200

    def test_list_with_feedback_filter(self, client):
        for fb in ("up", "down", "none"):
            r = client.get("/api/v1/sessions", params={"feedback": fb})
            assert r.status_code == 200

    def test_list_with_duration_range(self, client):
        r = client.get("/api/v1/sessions", params={"duration_min": 0, "duration_max": 99999})
        assert r.status_code == 200

    def test_list_with_sorting(self, client):
        r = client.get(
            "/api/v1/sessions",
            params={"sort_by": "duration_ms", "sort_dir": "asc"},
        )
        assert r.status_code == 200

    def test_list_with_pagination(self, client):
        r = client.get("/api/v1/sessions", params={"limit": 10, "offset": 0})
        assert r.status_code == 200

    def test_list_combined_filters(self, client):
        r = client.get(
            "/api/v1/sessions",
            params={"workflow": "default", "node": "generate", "limit": 5},
        )
        assert r.status_code == 200


class TestSessionTurns:
    """GET /api/v1/sessions/{chat_id} — get session turns."""

    def test_get_unknown_session_turns(self, client):
        r = client.get("/api/v1/sessions/chat_unknown_xyz")
        assert r.status_code == 404


class TestTurnDetail:
    """GET /api/v1/sessions/{chat_id}/turns/{turn_id} — turn node details."""

    def test_get_unknown_turn(self, client):
        r = client.get("/api/v1/sessions/chat_test/turns/99999")
        assert r.status_code == 404

    def test_get_unknown_node(self, client):
        r = client.get("/api/v1/sessions/chat_test/turns/0/nodes/unknown_node")
        assert r.status_code == 404
