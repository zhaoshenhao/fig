"""Client-perspective tests for document upload and scan endpoints."""

from __future__ import annotations

from unittest.mock import patch

_Q = "src.api.routes_admin.make_qdrant"
_E = "src.api.routes_admin.make_embed_client"
_M = "src.api.routes_admin.embed_model_name"
_B = "src.ingestion.builder.build_document"
_D = "src.ingestion.builder.build_directory"


class TestUpload:
    """POST /documents/upload — upload and index a document file."""

    def test_upload_requires_file(self, client):
        r = client.post("/documents/upload")
        assert r.status_code == 422

    def test_upload_success(self, client):
        with (
            patch(_Q),
            patch(_E),
            patch(_M, return_value="test-model"),
            patch(_B, return_value=5),
        ):
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

    def test_upload_with_custom_chunk_params(self, client):
        with (
            patch(_Q),
            patch(_E),
            patch(_M, return_value="m"),
            patch(_B, return_value=3),
        ):
            r = client.post(
                "/documents/upload",
                files={"file": ("doc.txt", b"content", "text/plain")},
                data={
                    "collection": "test",
                    "chunk_size": "512",
                    "chunk_overlap": "128",
                },
            )
            assert r.status_code == 200

    def test_upload_with_rebuild(self, client):
        with (
            patch(_Q) as mq,
            patch(_E),
            patch(_M, return_value="m"),
            patch(_B, return_value=2),
        ):
            r = client.post(
                "/documents/upload",
                files={"file": ("f.txt", b"x", "text/plain")},
                data={"collection": "rebuild_col", "rebuild": "true"},
            )
            assert r.status_code == 200
            assert r.json()["rebuilt"] is True


class TestScan:
    """POST /documents/scan — scan and index a directory."""

    def test_scan_invalid_directory(self, client):
        r = client.post("/documents/scan", data={"directory": "/nonexistent/xyz"})
        assert r.status_code == 400

    def test_scan_success(self, client, tmp_path):
        (tmp_path / "a.txt").write_text("test content", encoding="utf-8")

        with (
            patch(_Q),
            patch(_E),
            patch(_M, return_value="m"),
            patch(_D, return_value=7),
        ):
            r = client.post(
                "/documents/scan",
                data={
                    "directory": str(tmp_path),
                    "collection": "scanned_col",
                    "chunk_size": "256",
                },
            )
            assert r.status_code == 200
            data = r.json()
            assert data["status"] == "ok"
            assert data["chunks"] == 7

    def test_scan_with_rebuild(self, client, tmp_path):
        (tmp_path / "b.txt").write_text("more content", encoding="utf-8")

        with (
            patch(_Q) as mq,
            patch(_E),
            patch(_M, return_value="m"),
            patch(_D, return_value=3),
        ):
            r = client.post(
                "/documents/scan",
                data={
                    "directory": str(tmp_path),
                    "collection": "rebuild_scan",
                    "rebuild": "true",
                },
            )
            assert r.status_code == 200
            assert r.json()["rebuilt"] is True
