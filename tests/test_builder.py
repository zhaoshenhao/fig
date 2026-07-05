from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_proj_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_proj_root))

from src.ingestion.builder import (
    _iter_files,
    _point_id,
    build_directory,
    build_document,
)
from src.ingestion.chunker import (
    _merge_paragraphs,
    _read_markdown,
    _split_paragraphs,
    chunk_file,
    chunk_text,
)


class TestChunkText:
    def test_chunk_text_basic(self):
        paragraphs = [" ".join(["word"] * 10) for _ in range(10)]
        text = "\n\n".join(paragraphs)
        chunks = chunk_text(text, chunk_size=25, overlap=5)
        assert len(chunks) >= 2
        for c in chunks:
            assert c.strip()

    def test_chunk_text_empty(self):
        chunks = chunk_text("")
        assert chunks == []

    def test_chunk_text_short(self):
        text = "hello world"
        chunks = chunk_text(text, chunk_size=512, overlap=64)
        assert len(chunks) == 1
        assert chunks[0] == "hello world"


class TestSplitParagraphs:
    def test_split_paragraphs(self):
        text = "para1\n\npara2\n\n\npara3"
        result = _split_paragraphs(text)
        assert result == ["para1", "para2", "para3"]

    def test_split_paragraphs_single(self):
        result = _split_paragraphs("only one")
        assert result == ["only one"]

    def test_split_paragraphs_whitespace(self):
        result = _split_paragraphs("  a  \n\n  b  ")
        assert result == ["a", "b"]


class TestMergeParagraphs:
    def test_merge_paragraphs_overlap(self):
        paragraphs = ["a", "b", "c", "d", "e", "f", "g"]
        chunks = _merge_paragraphs(paragraphs, chunk_size=3, overlap=2)
        assert len(chunks) >= 3
        assert chunks[0] == "a\n\nb\n\nc"
        assert "b" in chunks[1]
        assert "c" in chunks[1]

    def test_merge_paragraphs_single(self):
        paragraphs = ["short text here"]
        chunks = _merge_paragraphs(paragraphs, chunk_size=512, overlap=64)
        assert len(chunks) == 1
        assert chunks[0] == "short text here"

    def test_merge_paragraphs_no_overlap(self):
        paragraphs = ["one two", "three four", "five six"]
        chunks = _merge_paragraphs(paragraphs, chunk_size=2, overlap=0)
        assert len(chunks) == 3


class TestChunkFile:
    def test_chunk_file_txt(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("hello world\n\nmore text here", encoding="utf-8")
        chunks = chunk_file(str(f))
        assert len(chunks) >= 1
        assert any("hello" in c for c in chunks)

    def test_chunk_file_md(self, tmp_path):
        f = tmp_path / "doc.md"
        f.write_text("# Title\n\nSome **bold** content with [link](url)", encoding="utf-8")
        chunks = chunk_file(str(f))
        assert len(chunks) >= 1
        full = "\n".join(chunks)
        assert "**" not in full
        assert "#" not in full
        assert "[" not in full
        assert "Title" in full
        assert "bold" in full

    def test_chunk_file_unsupported(self, tmp_path):
        f = tmp_path / "doc.xyz"
        f.write_text("content", encoding="utf-8")
        with pytest.raises(ValueError, match="unsupported"):
            chunk_file(str(f))

    def test_chunk_file_unsupported_unknown_ext(self, tmp_path):
        f = tmp_path / "doc.dat"
        f.write_text("content", encoding="utf-8")
        with pytest.raises(ValueError, match="unsupported"):
            chunk_file(str(f))

    def test_chunk_file_nonexistent(self):
        with pytest.raises(FileNotFoundError):
            chunk_file("/nonexistent/path/to/file.txt")


class TestReadMarkdown:
    def test_read_markdown_cleans_markup(self, tmp_path):
        f = tmp_path / "doc.md"
        f.write_text(
            "# Header\n\nText with **bold** and [link](http://example.com)",
            encoding="utf-8",
        )
        text = _read_markdown(f)
        assert "#" not in text
        assert "**" not in text
        assert "[" not in text
        assert "](" not in text
        assert "Header" in text
        assert "bold" in text
        assert "link" in text

    def test_read_markdown_underscore_emphasis(self, tmp_path):
        f = tmp_path / "doc.md"
        f.write_text("Some _italic_ and __bold__ text", encoding="utf-8")
        text = _read_markdown(f)
        assert "_" not in text
        assert "italic" in text


class TestBuildDocument:
    def test_build_document(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world", encoding="utf-8")

        mock_embed = MagicMock(return_value=[[0.1, 0.2, 0.3]])
        mock_client = MagicMock()
        mock_client.embed = mock_embed
        mock_qdrant = MagicMock()

        count = build_document(
            str(f), "test_col", mock_qdrant, mock_client, "test-model",
        )
        assert count == 1
        mock_qdrant.ensure_collection.assert_called_once_with(
            "test_col", vector_size=3,
        )
        mock_qdrant.upsert.assert_called_once()
        upsert_args = mock_qdrant.upsert.call_args[0]
        assert upsert_args[0] == "test_col"
        assert len(upsert_args[1]) == 1
        point = upsert_args[1][0]
        assert point["payload"]["text"] == "hello world"
        assert point["payload"]["source"] == "test.txt"
        assert point["payload"]["chunk_index"] == 0
        assert point["payload"]["total_chunks"] == 1

    def test_build_document_multiple_chunks(self, tmp_path):
        f = tmp_path / "chunked.txt"
        paragraphs = [" ".join(["word"] * 15) for _ in range(10)]
        f.write_text("\n\n".join(paragraphs), encoding="utf-8")

        mock_embed = MagicMock()
        mock_embed.side_effect = lambda _model, texts: [[0.1] * 10] * len(texts)
        mock_client = MagicMock()
        mock_client.embed = mock_embed
        mock_qdrant = MagicMock()

        count = build_document(
            str(f), "col", mock_qdrant, mock_client, "model",
            chunk_size=35, chunk_overlap=10,
        )
        assert count >= 2
        mock_client.embed.assert_called_once()
        upsert_args = mock_qdrant.upsert.call_args[0]
        assert len(upsert_args[1]) == count

    def test_build_document_empty_chunks(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("", encoding="utf-8")

        mock_client = MagicMock()
        mock_qdrant = MagicMock()

        count = build_document(
            str(f), "test_col", mock_qdrant, mock_client, "model",
        )
        assert count == 0
        mock_client.embed.assert_not_called()
        mock_qdrant.upsert.assert_not_called()

    def test_build_document_whitespace_only(self, tmp_path):
        f = tmp_path / "blank.txt"
        f.write_text("   \n\n   ", encoding="utf-8")

        mock_client = MagicMock()
        mock_qdrant = MagicMock()

        count = build_document(
            str(f), "test_col", mock_qdrant, mock_client, "model",
        )
        assert count == 0
        mock_client.embed.assert_not_called()


class TestBuildDirectory:
    def test_build_directory(self, tmp_path):
        (tmp_path / "a.txt").write_text("file a content", encoding="utf-8")
        (tmp_path / "b.txt").write_text("file b content", encoding="utf-8")
        (tmp_path / "ignored.xyz").write_text("skip me", encoding="utf-8")

        mock_embed = MagicMock(return_value=[[0.1, 0.2]])
        mock_client = MagicMock()
        mock_client.embed = mock_embed
        mock_qdrant = MagicMock()

        count = build_directory(
            str(tmp_path), "col", mock_qdrant, mock_client, "model",
            extensions=(".txt",),
        )
        assert count == 2

    def test_build_directory_default_extensions(self, tmp_path):
        (tmp_path / "a.txt").write_text("txt", encoding="utf-8")
        (tmp_path / "b.md").write_text("# md", encoding="utf-8")
        (tmp_path / "c.xyz").write_text("skip", encoding="utf-8")

        mock_embed = MagicMock(return_value=[[0.1, 0.2]])
        mock_client = MagicMock()
        mock_client.embed = mock_embed
        mock_qdrant = MagicMock()

        count = build_directory(
            str(tmp_path), "col", mock_qdrant, mock_client, "model",
        )
        assert count == 2

    def test_build_directory_subdirs(self, tmp_path):
        (tmp_path / "a.txt").write_text("top", encoding="utf-8")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "b.txt").write_text("nested", encoding="utf-8")

        mock_embed = MagicMock(return_value=[[0.1]])
        mock_client = MagicMock()
        mock_client.embed = mock_embed
        mock_qdrant = MagicMock()

        count = build_directory(
            str(tmp_path), "col", mock_qdrant, mock_client, "model",
            extensions=(".txt",),
        )
        assert count == 2

    def test_build_directory_not_a_dir(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("test", encoding="utf-8")

        mock_client = MagicMock()
        mock_qdrant = MagicMock()

        with pytest.raises(NotADirectoryError):
            build_directory(str(f), "col", mock_qdrant, mock_client, "model")

    def test_build_directory_not_found(self):
        mock_client = MagicMock()
        mock_qdrant = MagicMock()

        with pytest.raises(NotADirectoryError):
            build_directory(
                "/nonexistent/path/12345", "col", mock_qdrant, mock_client, "model",
            )


class TestPointID:
    def test_point_id_deterministic(self):
        a = _point_id("doc.txt", 0)
        b = _point_id("doc.txt", 0)
        assert a == b
        assert isinstance(a, int)

    def test_point_id_different_source(self):
        a = _point_id("a.txt", 0)
        b = _point_id("b.txt", 0)
        assert a != b

    def test_point_id_different_index(self):
        a = _point_id("doc.txt", 0)
        b = _point_id("doc.txt", 1)
        assert a != b


class TestIterFiles:
    def test_iter_files_filters_by_extension(self, tmp_path):
        (tmp_path / "a.txt").write_text("a", encoding="utf-8")
        (tmp_path / "b.txt").write_text("b", encoding="utf-8")
        (tmp_path / "c.md").write_text("c", encoding="utf-8")
        (tmp_path / "d.xyz").write_text("d", encoding="utf-8")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "e.txt").write_text("e", encoding="utf-8")
        (sub / "f.md").write_text("f", encoding="utf-8")

        files = list(_iter_files(tmp_path, (".txt",)))
        assert len(files) == 3
        names = {f.name for f in files}
        assert names == {"a.txt", "b.txt", "e.txt"}

    def test_iter_files_no_match(self, tmp_path):
        (tmp_path / "a.xyz").write_text("a", encoding="utf-8")
        (tmp_path / "b.abc").write_text("b", encoding="utf-8")

        files = list(_iter_files(tmp_path, (".txt", ".md")))
        assert files == []

    def test_iter_files_is_sorted(self, tmp_path):
        (tmp_path / "z.txt").write_text("z", encoding="utf-8")
        (tmp_path / "a.txt").write_text("a", encoding="utf-8")
        (tmp_path / "m.txt").write_text("m", encoding="utf-8")

        files = list(_iter_files(tmp_path, (".txt",)))
        names = [f.name for f in files]
        assert names == sorted(names)
