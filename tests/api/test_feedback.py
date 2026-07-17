"""Client-perspective tests for feedback endpoints."""

from __future__ import annotations


class TestSubmitFeedback:
    """POST /api/v1/sessions/{chat_id}/turns/{turn_id}/feedback"""

    def test_submit_up(self, client):
        r = client.post(
            "/api/v1/sessions/chat_fb/turns/0/feedback",
            json={"rating": "up"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["rating"] == "up"

    def test_submit_down(self, client):
        r = client.post(
            "/api/v1/sessions/chat_fb_down/turns/1/feedback",
            json={"rating": "down"},
        )
        assert r.status_code == 200
        assert r.json()["rating"] == "down"

    def test_submit_with_comment(self, client):
        r = client.post(
            "/api/v1/sessions/chat_fb_comment/turns/0/feedback",
            json={"rating": "up", "comment": "very helpful"},
        )
        assert r.status_code == 200
        assert r.json()["rating"] == "up"

    def test_submit_with_correction(self, client):
        r = client.post(
            "/api/v1/sessions/chat_fb_correction/turns/0/feedback",
            json={"rating": "down", "correction": "the correct answer is X"},
        )
        assert r.status_code == 200

    def test_invalid_rating_rejected(self, client):
        r = client.post(
            "/api/v1/sessions/c/turns/0/feedback",
            json={"rating": "maybe"},
        )
        assert r.status_code == 422


class TestGetFeedback:
    """GET /api/v1/sessions/{chat_id}/turns/{turn_id}/feedback"""

    def test_get_feedback(self, client):
        r = client.get("/api/v1/sessions/chat_fb/turns/0/feedback")
        assert r.status_code == 200
        data = r.json()
        assert "feedback" in data
        assert isinstance(data["feedback"], list)


class TestFeedbackPersistence:
    """Verify feedback is stored and retrievable."""

    def test_submit_then_get(self, client):
        cid = "fb_roundtrip"
        tid = 0
        client.post(
            f"/api/v1/sessions/{cid}/turns/{tid}/feedback",
            json={"rating": "up", "comment": "roundtrip test"},
        )
        r = client.get(f"/api/v1/sessions/{cid}/turns/{tid}/feedback")
        assert r.status_code == 200
        ratings = [f["rating"] for f in r.json()["feedback"]]
        assert "up" in ratings
