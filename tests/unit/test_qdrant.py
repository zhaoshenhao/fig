from __future__ import annotations

import sys
from pathlib import Path

_proj_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_proj_root))


class TestQdrantSearch:
    def test_init_default_params(self, mocker):
        mock_qdrant_cls = mocker.patch("src.rag.qdrant.QdrantClient")
        from src.rag.qdrant import QdrantSearch

        QdrantSearch()
        mock_qdrant_cls.assert_called_once_with(
            host="localhost", port=6334, prefer_grpc=True
        )

    def test_init_custom_host_port(self, mocker):
        mock_qdrant_cls = mocker.patch("src.rag.qdrant.QdrantClient")
        from src.rag.qdrant import QdrantSearch

        QdrantSearch(host="10.0.0.1", port=9999)
        mock_qdrant_cls.assert_called_once_with(
            host="10.0.0.1", port=9999, prefer_grpc=True
        )

    def test_ensure_collection_creates_when_not_exists(self, mocker):
        mock_qdrant_cls = mocker.patch("src.rag.qdrant.QdrantClient")
        mock_client = mock_qdrant_cls.return_value
        mock_client.collection_exists.return_value = False

        from src.rag.qdrant import QdrantSearch

        q = QdrantSearch()
        q.ensure_collection("test_col", 768)

        mock_client.collection_exists.assert_called_once_with("test_col")
        mock_client.create_collection.assert_called_once()

    def test_ensure_collection_skips_when_exists(self, mocker):
        mock_qdrant_cls = mocker.patch("src.rag.qdrant.QdrantClient")
        mock_client = mock_qdrant_cls.return_value
        mock_client.collection_exists.return_value = True

        from src.rag.qdrant import QdrantSearch

        q = QdrantSearch()
        q.ensure_collection("test_col")

        mock_client.create_collection.assert_not_called()

    def test_upsert_creates_points(self, mocker):
        mock_qdrant_cls = mocker.patch("src.rag.qdrant.QdrantClient")

        from src.rag.qdrant import QdrantSearch

        q = QdrantSearch()
        points = [
            {"id": 1, "vector": [0.1] * 768, "payload": {"text": "hello"}},
        ]
        q.upsert("test_col", points)

        mock_qdrant_cls.return_value.upsert.assert_called_once()

    def test_search_vector_fallback(self, mocker):
        mock_qdrant_cls = mocker.patch("src.rag.qdrant.QdrantClient")
        mock_client = mock_qdrant_cls.return_value

        fake_point = mocker.MagicMock()
        fake_point.id = 1
        fake_point.score = 0.95
        fake_point.payload = {"text": "result doc"}
        mock_client.query_points.return_value.points = [fake_point]

        from src.rag.qdrant import QdrantSearch

        q = QdrantSearch()
        results = q.search(
            collection="test_col",
            vector=[0.1] * 768,
            query_text="",
            limit=10,
        )

        assert len(results) == 1
        assert results[0]["id"] == 1
        assert results[0]["score"] == 0.95

    def test_search_hybrid_with_query_text(self, mocker):
        mock_qdrant_cls = mocker.patch("src.rag.qdrant.QdrantClient")
        mock_client = mock_qdrant_cls.return_value

        fake_point = mocker.MagicMock()
        fake_point.id = 2
        fake_point.score = 0.88
        fake_point.payload = {"text": "hybrid result"}
        mock_client.query_points.return_value.points = [fake_point]

        from src.rag.qdrant import QdrantSearch

        q = QdrantSearch()
        results = q.search(
            collection="test_col",
            vector=[0.1] * 768,
            query_text="search terms",
            limit=10,
            prefetch_limit=20,
        )

        assert len(results) == 1
        assert results[0]["id"] == 2

    def test_search_hybrid_fallback_on_error(self, mocker):
        mock_qdrant_cls = mocker.patch("src.rag.qdrant.QdrantClient")
        mock_client = mock_qdrant_cls.return_value

        fake_point = mocker.MagicMock()
        fake_point.id = 3
        fake_point.score = 0.7
        fake_point.payload = {}
        mock_client.query_points.side_effect = [
            Exception("hybrid failed"),
            mocker.MagicMock(points=[fake_point]),
        ]

        from src.rag.qdrant import QdrantSearch

        q = QdrantSearch()
        results = q.search(
            collection="test_col",
            vector=[0.1] * 768,
            query_text="will fail",
        )

        assert len(results) == 1
        assert results[0]["id"] == 3

    def test_scroll_returns_records(self, mocker):
        mock_qdrant_cls = mocker.patch("src.rag.qdrant.QdrantClient")
        mock_client = mock_qdrant_cls.return_value

        fake_record = mocker.MagicMock()
        fake_record.id = 10
        fake_record.payload = {"text": "page content"}

        mock_client.scroll.return_value = ([fake_record], None)

        from src.rag.qdrant import QdrantSearch

        q = QdrantSearch()
        records, next_offset = q.scroll("test_col", limit=20, offset=0)

        assert len(records) == 1
        assert records[0]["id"] == 10
        assert next_offset is None

    def test_scroll_with_next_offset(self, mocker):
        mock_qdrant_cls = mocker.patch("src.rag.qdrant.QdrantClient")
        mock_client = mock_qdrant_cls.return_value

        fake_record = mocker.MagicMock()
        fake_record.id = 20
        fake_record.payload = {}
        next_id = mocker.MagicMock()
        next_id.to_int.return_value = 50

        mock_client.scroll.return_value = ([fake_record], next_id)

        from src.rag.qdrant import QdrantSearch

        q = QdrantSearch()
        _records, next_offset = q.scroll("test_col", limit=20, offset=0)

        assert next_offset == 50
