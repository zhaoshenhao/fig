"""Client-perspective tests for collection endpoints.

These tests mock the Qdrant client to avoid external dependencies.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

_Q = "src.api.routes_admin.make_qdrant"
_E = "src.api.routes_admin.make_embed_client"
_M = "src.api.routes_admin.embed_model_name"


class TestCollectionList:
    """GET /collections — list all collections."""

    def test_list_collections_returns_200(self, client):
        with patch(_Q) as m:
            m.return_value.list_collections.return_value = ["default", "car_film"]
            r = client.get("/collections")
            assert r.status_code == 200
            data = r.json()
            assert "collections" in data


class TestCollectionDetail:
    """GET /collections/{name} — get collection info."""

    def test_get_collection(self, client):
        with patch(_Q) as m:
            m.return_value.collection_info.return_value = {
                "name": "default", "vectors_count": 42,
            }
            r = client.get("/collections/default")
            assert r.status_code == 200
            data = r.json()
            assert data["name"] == "default"

    def test_get_nonexistent_collection(self, client):
        with patch(_Q) as m:
            m.return_value.collection_info.side_effect = ValueError("not found")
            r = client.get("/collections/nonexistent_col")
            assert r.status_code == 404


class TestCollectionDelete:
    """DELETE /collections/{name} — delete a collection."""

    def test_delete_collection(self, client):
        with patch(_Q) as m:
            r = client.delete("/collections/test_col")
            assert r.status_code == 200
            assert r.json()["status"] == "deleted"
            m.return_value.delete_collection.assert_called_once_with("test_col")


class TestCollectionDeletePoints:
    """DELETE /collections/{name}/points — delete specific points."""

    def test_delete_points(self, client):
        with patch(_Q) as m:
            m.return_value.delete_points.return_value = {"deleted": 3}
            r = client.request(
                "DELETE", "/collections/foo/points",
                json={"ids": [1, 2, 3]},
            )
            assert r.status_code == 200

    def test_delete_points_requires_ids(self, client):
        r = client.request("DELETE", "/collections/foo/points", json={"ids": []})
        assert r.status_code == 422


class TestCollectionBrowse:
    """GET /collections/{name}/browse — scroll through documents."""

    def test_browse_collection(self, client):
        with patch(_Q) as m:
            m.return_value.scroll.return_value = (
                [{"id": 1, "payload": {"text": "hello"}}],
                0,
            )
            r = client.get("/collections/test/browse")
            assert r.status_code == 200
            data = r.json()
            assert data["collection"] == "test"
            assert data["next_offset"] == 0

    def test_browse_with_pagination(self, client):
        with patch(_Q) as m:
            m.return_value.scroll.return_value = ([], None)
            r = client.get("/collections/test/browse",
                           params={"limit": 10, "offset": 20})
            assert r.status_code == 200


class TestCollectionSearch:
    """GET /collections/{name}/search — semantic search."""

    def test_search_requires_query(self, client):
        r = client.get("/collections/foo/search")
        assert r.status_code == 422

    def test_search_returns_results(self, client):
        with (
            patch(_Q) as mq,
            patch(_E) as me,
            patch(_M, return_value="test-model"),
        ):
            mq.return_value.search.return_value = [{
                "id": 1, "score": 0.95,
                "payload": {"text": "result text", "source": "doc.md"},
            }]
            me.return_value.embed.return_value = [[0.1, 0.2, 0.3]]
            r = client.get("/collections/test/search", params={"q": "query"})
            assert r.status_code == 200
            data = r.json()
            assert data["query"] == "query"
            assert len(data["points"]) == 1
            assert data["points"][0]["text"] == "result text"

    def test_search_returns_empty(self, client):
        with (
            patch(_Q) as mq,
            patch(_E) as me,
            patch(_M, return_value="test-model"),
        ):
            mq.return_value.search.return_value = []
            me.return_value.embed.return_value = [[0.1]]
            r = client.get("/collections/test/search", params={"q": "no results"})
            assert r.status_code == 200
            assert r.json()["points"] == []


class TestCollectionCount:
    """GET /collections/{name}/count — count points."""

    def test_count_collection(self, client):
        with patch(_Q) as m:
            m.return_value.count.return_value = 100
            r = client.get("/collections/test/count")
            assert r.status_code == 200
            assert r.json()["count"] == 100
