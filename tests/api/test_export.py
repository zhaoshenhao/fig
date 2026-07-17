"""Client-perspective tests for export endpoints."""

from __future__ import annotations


class TestExportXLSX:
    """POST /export/chat.xlsx — export chat to Excel."""

    def test_export_basic(self, client):
        r = client.post("/export/chat.xlsx", json={
            "messages": [
                {"role": "user", "content": "hello", "ts": "10:00"},
                {"role": "assistant", "content": "hi there", "ts": "10:01"},
            ],
            "filename": "my chat",
        })
        assert r.status_code == 200
        assert "spreadsheetml" in r.headers["content-type"]
        assert "mychat.xlsx" in r.headers["content-disposition"]
        assert r.content[:2] == b"PK"  # ZIP magic bytes

    def test_export_empty_messages(self, client):
        r = client.post("/export/chat.xlsx", json={"messages": []})
        assert r.status_code == 200
        assert r.content[:2] == b"PK"

    def test_export_with_feedback(self, client):
        r = client.post("/export/chat.xlsx", json={
            "messages": [
                {"role": "assistant", "content": "answer",
                 "feedback": "down", "comment": "bad", "correction": "fixed"},
            ],
        })
        assert r.status_code == 200
        assert r.content[:2] == b"PK"

    def test_filename_sanitization(self, client):
        r = client.post("/export/chat.xlsx", json={
            "messages": [{"role": "user", "content": "x"}],
            "filename": "my chat!@#$%^",
        })
        assert r.status_code == 200
        # Filename should be sanitized
        assert "mychat" in r.headers["content-disposition"]


class TestExportCSV:
    """POST /export/chat.csv — export chat to CSV."""

    def test_export_basic(self, client):
        r = client.post("/export/chat.csv", json={
            "messages": [{"role": "assistant", "content": "hi", "ts": "t"}],
        })
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
        body = r.content.decode("utf-8")
        assert body.startswith("\ufeff")  # BOM
        assert "role,content,timestamp,feedback,comment,correction" in body

    def test_export_with_feedback_data(self, client):
        r = client.post("/export/chat.csv", json={
            "messages": [{
                "role": "assistant", "content": "x",
                "feedback": "down", "comment": "bad", "correction": "fix",
            }],
        })
        assert r.status_code == 200
        body = r.content.decode("utf-8")
        assert "down" in body
        assert "fix" in body

    def test_export_empty(self, client):
        r = client.post("/export/chat.csv", json={"messages": []})
        assert r.status_code == 200


class TestExportTraining:
    """GET /export/training.jsonl — export training data."""

    def test_export_with_limit(self, client):
        r = client.get("/export/training.jsonl", params={"limit": 5})
        assert r.status_code == 200
        assert "ndjson" in r.headers["content-type"]

    def test_export_with_workflow_filter(self, client):
        r = client.get("/export/training.jsonl",
                        params={"workflow": "default", "limit": 2})
        assert r.status_code == 200

    def test_export_only_feedback(self, client):
        r = client.get("/export/training.jsonl",
                        params={"limit": 5, "only_feedback": "1"})
        assert r.status_code == 200
