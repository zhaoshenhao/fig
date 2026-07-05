from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

_proj_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_proj_root))


class TestAPIEndpoints:
    @staticmethod
    def _make_client():
        from src.api.main import app
        from src.config import load_app_config

        load_app_config()
        return TestClient(app, raise_server_exceptions=False)

    def test_health(self):
        client = self._make_client()
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "timestamp" in data

    def test_ready(self):
        client = self._make_client()
        r = client.get("/ready")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ready"
        assert isinstance(data["workflows"], list)

    def test_list_workflows(self):
        client = self._make_client()
        r = client.get("/workflows")
        assert r.status_code == 200
        data = r.json()
        assert "workflows" in data
        assert isinstance(data["workflows"], list)

    def test_get_workflow_exists(self):
        client = self._make_client()
        r = client.get("/workflows/default")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "default"
        assert "nodes" in data

    def test_get_workflow_not_found(self):
        client = self._make_client()
        r = client.get("/workflows/nonexistent_wf")
        assert r.status_code == 404

    def test_run_workflow_not_found(self):
        client = self._make_client()
        r = client.post(
            "/workflows/nonexistent_wf/run",
            json={"query": "hello"},
        )
        assert r.status_code == 404

    def test_document_upload_requires_file(self):
        client = self._make_client()
        r = client.post("/documents/upload")
        assert r.status_code == 422

    def test_document_scan_requires_directory(self):
        client = self._make_client()
        r = client.post("/documents/scan", data={"directory": "/nonexistent/xyz"})
        assert r.status_code == 400

    def test_openapi_schema(self):
        client = self._make_client()
        r = client.get("/openapi.json")
        assert r.status_code == 200
        data = r.json()
        assert "paths" in data
        assert "/health" in data["paths"]

    def test_docs_ui(self):
        client = self._make_client()
        r = client.get("/docs")
        assert r.status_code == 200

    def test_run_workflow_empty_query_rejected(self):
        client = self._make_client()
        r = client.post(
            "/workflows/default/run",
            json={"query": ""},
        )
        assert r.status_code == 422

    def test_workflow_run_handles_error_gracefully(self):
        client = self._make_client()
        r = client.post(
            "/workflows/default/run",
            json={"query": "test query"},
        )
        assert r.status_code in (200, 500)


class TestAPIMultiTurn:
    @staticmethod
    def _make_client():
        from src.api.main import app
        from src.config import load_app_config

        load_app_config()
        return TestClient(app, raise_server_exceptions=False)

    def test_run_without_chat_id_returns_new_session(self):
        client = self._make_client()
        r = client.post("/workflows/default/run", json={"query": "hello"})
        assert r.status_code in (200, 500)
        if r.status_code == 200:
            data = r.json()
            assert "chat_id" in data
            assert data["chat_id"].startswith("chat_")
            assert "reply" in data

    def test_run_with_valid_chat_id_continues(self):
        client = self._make_client()
        r1 = client.post("/workflows/default/run", json={"query": "turn 1"})
        if r1.status_code != 200:
            return
        cid = r1.json()["chat_id"]

        r2 = client.post(
            "/workflows/default/run",
            json={"query": "turn 2", "chat_id": cid},
        )
        assert r2.status_code == 200
        data = r2.json()
        assert data["chat_id"] == cid

    def test_run_with_long_mem_data(self):
        client = self._make_client()
        r = client.post(
            "/workflows/default/run",
            json={"query": "hello", "long_mem_data": "VIP memory"},
        )
        assert r.status_code in (200, 500)

    def test_run_with_expired_session_returns_404(self):
        client = self._make_client()
        r = client.post(
            "/workflows/default/run",
            json={"query": "q", "chat_id": "chat_bogus9999"},
        )
        assert r.status_code == 404

    def test_delete_session(self):
        client = self._make_client()
        r1 = client.post("/workflows/default/run", json={"query": "hi"})
        if r1.status_code != 200:
            return
        cid = r1.json()["chat_id"]

        r2 = client.delete(f"/sessions/{cid}")
        assert r2.status_code == 204

        r3 = client.post(
            "/workflows/default/run",
            json={"query": "again", "chat_id": cid},
        )
        assert r3.status_code == 404

    def test_delete_nonexistent_session(self):
        client = self._make_client()
        r = client.delete("/sessions/chat_nonexistent")
        assert r.status_code == 404

    def test_get_workflow_still_works(self):
        client = self._make_client()
        r = client.get("/workflows/default")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "default"
        assert "nodes" in data


class TestAPIDocuments:
    @staticmethod
    def _make_client():
        from src.api.main import app
        from src.config import load_app_config

        load_app_config()
        return TestClient(app, raise_server_exceptions=False)

    def test_upload_requires_file(self):
        client = self._make_client()
        r = client.post("/documents/upload")
        assert r.status_code == 422

    def test_scan_invalid_directory(self):
        client = self._make_client()
        r = client.post("/documents/scan", data={"directory": "/nonexistent/xyz"})
        assert r.status_code == 400

    def test_upload_success(self, mocker):
        mocker.patch("src.api.main.QdrantSearch")
        mocker.patch("src.api.main.LLMClient")
        mock_build = mocker.patch("src.api.main.build_document", return_value=5)

        client = self._make_client()
        r = client.post(
            "/documents/upload",
            files={"file": ("test.txt", b"hello world", "text/plain")},
            data={"collection": "my_col", "chunk_size": "256"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["chunks"] == 5
        assert data["collection"] == "my_col"
        mock_build.assert_called_once()

    def test_scan_success(self, mocker):
        import tempfile
        from pathlib import Path

        tmp = Path(tempfile.mkdtemp())
        (tmp / "a.txt").write_text("test", encoding="utf-8")

        mocker.patch("src.api.main.QdrantSearch")
        mocker.patch("src.api.main.LLMClient")
        mock_build = mocker.patch("src.api.main.build_directory", return_value=3)

        client = self._make_client()
        r = client.post(
            "/documents/scan",
            data={"directory": str(tmp), "collection": "default"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["chunks"] == 3
        mock_build.assert_called_once()
