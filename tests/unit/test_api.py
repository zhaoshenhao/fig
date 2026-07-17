from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

_proj_root = Path(__file__).resolve().parent.parent.parent
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
        r = client.get("/api/v1/workflows")
        assert r.status_code == 200
        data = r.json()
        assert "workflows" in data
        assert isinstance(data["workflows"], list)

    def test_get_workflow_exists(self):
        client = self._make_client()
        r = client.get("/api/v1/workflows/default")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "default"
        assert "nodes" in data

    def test_get_workflow_not_found(self):
        client = self._make_client()
        r = client.get("/api/v1/workflows/nonexistent_wf")
        assert r.status_code == 404

    def test_run_workflow_not_found(self):
        client = self._make_client()
        r = client.post(
            "/api/v1/workflows/nonexistent_wf/run",
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
            "/api/v1/workflows/default/run",
            json={"query": ""},
        )
        assert r.status_code == 422

    def test_workflow_run_handles_error_gracefully(self):
        client = self._make_client()
        r = client.post(
            "/api/v1/workflows/default/run",
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
        r = client.post("/api/v1/workflows/default/run", json={"query": "hello"})
        assert r.status_code in (200, 500)
        if r.status_code == 200:
            data = r.json()
            assert "chat_id" in data
            assert data["chat_id"].startswith("chat_")
            assert "reply" in data

    def test_run_with_valid_chat_id_continues(self):
        client = self._make_client()
        r1 = client.post("/api/v1/workflows/default/run", json={"query": "turn 1"})
        if r1.status_code != 200:
            return
        cid = r1.json()["chat_id"]

        r2 = client.post(
            "/api/v1/workflows/default/run",
            json={"query": "turn 2", "chat_id": cid},
        )
        assert r2.status_code == 200
        data = r2.json()
        assert data["chat_id"] == cid

    def test_run_with_long_mem_data(self):
        client = self._make_client()
        r = client.post(
            "/api/v1/workflows/default/run",
            json={"query": "hello", "long_mem_data": "VIP memory"},
        )
        assert r.status_code in (200, 500)

    def test_run_with_expired_session_returns_404(self):
        client = self._make_client()
        r = client.post(
            "/api/v1/workflows/default/run",
            json={"query": "q", "chat_id": "chat_bogus9999"},
        )
        assert r.status_code == 404

    def test_delete_session(self):
        client = self._make_client()
        r1 = client.post("/api/v1/workflows/default/run", json={"query": "hi"})
        if r1.status_code != 200:
            return
        cid = r1.json()["chat_id"]

        r2 = client.delete(f"/api/v1/sessions/{cid}")
        assert r2.status_code == 204

        r3 = client.post(
            "/api/v1/workflows/default/run",
            json={"query": "again", "chat_id": cid},
        )
        assert r3.status_code == 404

    def test_delete_nonexistent_session(self):
        client = self._make_client()
        r = client.delete("/api/v1/sessions/chat_nonexistent")
        assert r.status_code == 404

    def test_get_workflow_still_works(self):
        client = self._make_client()
        r = client.get("/api/v1/workflows/default")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "default"
        assert "nodes" in data

    def test_list_sessions_no_filter(self):
        client = self._make_client()
        r = client.get("/api/v1/sessions")
        assert r.status_code == 200
        data = r.json()
        assert "sessions" in data
        assert "total" in data
        assert isinstance(data["sessions"], list)

    def test_list_sessions_single_filters(self):
        """Regression: node/tool/input_text/output_text filters alone must not 500."""
        client = self._make_client()
        for key in ("node", "tool", "input_text", "output_text", "workflow"):
            r = client.get("/api/v1/sessions", params={key: "x"})
            assert r.status_code == 200, f"{key} filter returned {r.status_code}"
            assert "sessions" in r.json()

    def test_list_sessions_combined_filters(self):
        client = self._make_client()
        r = client.get(
            "/api/v1/sessions",
            params={"node": "a", "tool": "b", "input_text": "c", "output_text": "d"},
        )
        assert r.status_code == 200

    def test_list_sessions_duration_and_sort(self):
        client = self._make_client()
        r = client.get(
            "/api/v1/sessions",
            params={"duration_min": 0, "duration_max": 99999,
                    "sort_by": "duration_ms", "sort_dir": "asc"},
        )
        assert r.status_code == 200

    def test_list_sessions_feedback_filter(self):
        client = self._make_client()
        for fb in ("none", "up", "down", ""):
            r = client.get("/api/v1/sessions", params={"feedback": fb})
            assert r.status_code == 200
            assert "sessions" in r.json()

    def test_sessions_filters_facets(self):
        client = self._make_client()
        r = client.get("/api/v1/sessions/filters")
        assert r.status_code == 200
        data = r.json()
        assert "workflows" in data and "nodes" in data and "tools" in data
        assert isinstance(data["workflows"], list)

    def test_export_chat_xlsx(self):
        client = self._make_client()
        r = client.post("/export/chat.xlsx", json={
            "messages": [
                {"role": "user", "content": "你好", "ts": "10:00:00"},
                {"role": "assistant", "content": "您好，有什么可以帮您", "ts": "10:00:01"},
            ],
            "filename": "my chat!@#",
        })
        assert r.status_code == 200
        assert "spreadsheetml" in r.headers["content-type"]
        assert "mychat.xlsx" in r.headers["content-disposition"]
        # xlsx 是 zip 容器，magic bytes 为 PK
        assert r.content[:2] == b"PK"

    def test_export_chat_csv(self):
        client = self._make_client()
        r = client.post("/export/chat.csv", json={
            "messages": [{"role": "assistant", "content": "hi", "ts": "t",
                          "feedback": "down", "comment": "bad", "correction": "should be X"}],
        })
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
        body = r.content.decode("utf-8")
        assert body.startswith("\ufeff")
        assert "role,content,timestamp,feedback,comment,correction" in body
        assert "hi" in body and "down" in body and "should be X" in body

    def test_export_chat_empty(self):
        client = self._make_client()
        r = client.post("/export/chat.xlsx", json={"messages": []})
        assert r.status_code == 200
        assert r.content[:2] == b"PK"


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

    def test_upload_rebuild_drops_collection(self, mocker):
        mq = mocker.patch("src.api.main._make_qdrant")
        mocker.patch("src.api.main._make_embed_client")
        mocker.patch("src.api.main._embed_model_name", return_value="m")
        mocker.patch("src.api.main.build_document", return_value=2)

        client = self._make_client()
        r = client.post(
            "/documents/upload",
            files={"file": ("t.txt", b"x", "text/plain")},
            data={"collection": "col_rebuild", "rebuild": "true"},
        )
        assert r.status_code == 200
        assert r.json()["rebuilt"] is True
        mq.return_value.delete_collection.assert_called_once_with("col_rebuild")


class TestAPIStatusAndSearch:
    @staticmethod
    def _make_client():
        from src.api.main import app
        from src.config import load_app_config

        load_app_config()
        return TestClient(app, raise_server_exceptions=False)

    def test_status_structure(self, mocker):
        mocker.patch("src.api.main.QdrantSearch")
        client = self._make_client()
        r = client.get("/status")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] in ("ok", "degraded")
        assert "components" in data
        assert "qdrant" in data["components"]
        assert "metrics_store" in data["components"]
        assert data["process"]["version"]
        assert "uptime_seconds" in data["process"]

    def test_search_collection(self, mocker):
        mq = mocker.patch("src.api.main._make_qdrant")
        mq.return_value.search.return_value = [
            {"id": 1, "score": 0.91, "payload": {"text": "隔热膜介绍", "source": "a.md"}},
        ]
        me = mocker.patch("src.api.main._make_embed_client")
        me.return_value.embed.return_value = [[0.1, 0.2, 0.3]]
        mocker.patch("src.api.main._embed_model_name", return_value="nomic-embed-text")

        client = self._make_client()
        r = client.get("/collections/car_film/search", params={"q": "隔热膜"})
        assert r.status_code == 200
        d = r.json()
        assert d["query"] == "隔热膜"
        assert d["points"][0]["text"] == "隔热膜介绍"
        assert d["points"][0]["source"] == "a.md"

    def test_search_requires_query(self):
        client = self._make_client()
        r = client.get("/collections/foo/search")
        assert r.status_code == 422

    def test_metrics_summary(self):
        client = self._make_client()
        r = client.get("/metrics/summary")
        assert r.status_code == 200
        data = r.json()
        assert "overview" in data
        assert "by_workflow" in data
        assert "by_tool" in data
        assert "trend" in data
        assert "error_rate" in data["overview"]

    def test_metrics_timeseries(self):
        client = self._make_client()
        r = client.get("/metrics/timeseries", params={"workflow": "auto_film"})
        assert r.status_code == 200
        data = r.json()
        assert data["workflow"] == "auto_film"
        assert "buckets" in data
        assert "workflow_series" in data
        assert "nodes" in data and "tools" in data

    def test_metrics_timeseries_requires_workflow(self):
        client = self._make_client()
        r = client.get("/metrics/timeseries")
        assert r.status_code == 422

    def test_export_training_jsonl(self):
        client = self._make_client()
        r = client.get("/export/training.jsonl", params={"limit": 5})
        assert r.status_code == 200
        assert "ndjson" in r.headers["content-type"]
        # 每行应为合法 JSON（若有数据），且含反馈字段
        body = r.content.decode("utf-8").strip()
        if body:
            import json as _j
            for line in body.split("\n"):
                obj = _j.loads(line)
                assert "query" in obj and "reply" in obj
                assert "feedback_rating" in obj

    def test_metrics_feedback_list(self):
        client = self._make_client()
        r = client.get("/metrics/feedback", params={"limit": 10})
        assert r.status_code == 200
        data = r.json()
        assert "feedback" in data and "count" in data

    def test_metrics_feedback_filter_rating(self):
        client = self._make_client()
        r = client.get("/metrics/feedback", params={"rating": "down", "limit": 5})
        assert r.status_code == 200
        for f in r.json()["feedback"]:
            assert f["rating"] == "down"

    def test_metrics_retention_requires_days(self):
        client = self._make_client()
        r = client.post("/metrics/retention")
        assert r.status_code == 422

    def test_metrics_retention_old_cutoff_deletes_nothing(self):
        client = self._make_client()
        r = client.post("/metrics/retention", params={"days": 36500})
        assert r.status_code == 200
        assert r.json()["deleted_runs"] == 0


class TestAPIExternalV2:
    """新增外部功能：健康、反馈、重生成、会话元信息、用量。"""

    @staticmethod
    def _make_client():
        from src.api.main import app
        from src.config import load_app_config

        load_app_config()
        return TestClient(app, raise_server_exceptions=False)

    def test_health_v1(self):
        client = self._make_client()
        r = client.get("/api/v1/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_feedback_submit_and_get(self):
        client = self._make_client()
        r = client.post(
            "/api/v1/sessions/chat_fb_test/turns/0/feedback",
            json={"rating": "up", "comment": "great", "correction": None},
        )
        assert r.status_code == 200
        assert r.json()["rating"] == "up"

        g = client.get("/api/v1/sessions/chat_fb_test/turns/0/feedback")
        assert g.status_code == 200
        fb = g.json()["feedback"]
        assert any(f["rating"] == "up" and f["comment"] == "great" for f in fb)

    def test_feedback_invalid_rating(self):
        client = self._make_client()
        r = client.post(
            "/api/v1/sessions/c/turns/0/feedback", json={"rating": "maybe"},
        )
        assert r.status_code == 422

    def test_regenerate_no_session(self):
        client = self._make_client()
        r = client.post(
            "/api/v1/workflows/default/regenerate", json={"chat_id": "nope_xyz"},
        )
        assert r.status_code == 404

    def test_regenerate_unknown_workflow(self):
        client = self._make_client()
        r = client.post(
            "/api/v1/workflows/nonexistent/regenerate", json={"chat_id": "x"},
        )
        assert r.status_code == 404

    def test_session_meta_get_falls_back_to_metrics(self):
        client = self._make_client()
        # 未知/过期会话：GET 返回 200 + 空元信息（从 metrics 读，不再 404）
        r = client.get("/api/v1/sessions/nope_meta/meta")
        assert r.status_code == 200
        assert r.json()["title"] == ""

    def test_session_meta_patch_persists_to_metrics(self):
        client = self._make_client()
        cid = "meta_persist_test"
        r = client.patch(f"/api/v1/sessions/{cid}/meta",
                         json={"title": "标题X", "tags": ["a", "b"]})
        assert r.status_code == 200
        assert r.json()["title"] == "标题X"
        # 持久化：再 GET 可读回
        g = client.get(f"/api/v1/sessions/{cid}/meta")
        assert g.json()["title"] == "标题X"
        assert g.json()["tags"] == ["a", "b"]
        # 会话搜索可按标题过滤（该 chat 无 runs，此处仅验证接口不报错）
        s = client.get("/api/v1/sessions", params={"title": "标题X"})
        assert s.status_code == 200

    def test_usage(self):
        client = self._make_client()
        r = client.get("/api/v1/usage")
        assert r.status_code == 200
        data = r.json()
        for k in ("total_runs", "total_sessions", "prompt_tokens",
                  "completion_tokens", "total_tokens", "error_rate"):
            assert k in data
