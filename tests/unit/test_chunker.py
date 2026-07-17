from __future__ import annotations

import sys
from pathlib import Path

import pytest

_proj_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_proj_root))


class TestChunkText:
    def test_empty_text(self):
        from src.ingestion.chunker import chunk_text
        assert chunk_text("") == []

    def test_single_short_paragraph(self):
        from src.ingestion.chunker import chunk_text
        result = chunk_text("hello world")
        assert len(result) == 1
        assert result[0] == "hello world"

    def test_multiple_paragraphs_under_chunk_size(self):
        from src.ingestion.chunker import chunk_text
        text = "one\n\ntwo\n\nthree"
        result = chunk_text(text, chunk_size=50)
        assert len(result) == 1
        assert "one\n\ntwo\n\nthree" in result

    def test_splits_on_chunk_size(self):
        from src.ingestion.chunker import chunk_text
        text = "a b c\n\nd e f\n\ng h i\n\nj k l\n\nm n o"
        result = chunk_text(text, chunk_size=5)
        assert len(result) >= 2

    def test_overlap_between_chunks(self):
        from src.ingestion.chunker import chunk_text
        text = "first para\n\nsecond para\n\nthird para\n\nfourth para"
        result = chunk_text(text, chunk_size=4, overlap=2)
        assert len(result) >= 1


class TestChunkFile:
    def test_txt_file(self, tmp_path):
        from src.ingestion.chunker import chunk_file

        f = tmp_path / "doc.txt"
        f.write_text("paragraph one\n\nparagraph two", encoding="utf-8")
        result = chunk_file(str(f))
        assert len(result) == 1
        assert "paragraph one" in result[0]

    def test_md_file(self, tmp_path):
        from src.ingestion.chunker import chunk_file

        f = tmp_path / "doc.md"
        f.write_text("# Title\n\nSome content here.\n\nMore content.", encoding="utf-8")
        result = chunk_file(str(f))
        assert len(result) == 1
        assert "Title" in result[0]
        assert "Some content here" in result[0]

    def test_unsupported_extension_raises(self, tmp_path):
        from src.ingestion.chunker import chunk_file

        f = tmp_path / "doc.xyz"
        f.write_text("content", encoding="utf-8")
        with pytest.raises(ValueError, match="unsupported"):
            chunk_file(str(f))

    def test_pdf_raises_import_error_if_pymupdf_not_installed(self, tmp_path):
        f = tmp_path / "doc.pdf"

        import builtins
        orig_import = builtins.__import__

        def _fake_import(name, *args, **kwargs):
            if name == "pymupdf":
                raise ImportError()
            return orig_import(name, *args, **kwargs)

        builtins.__import__ = _fake_import
        try:
            from importlib import reload

            import src.ingestion.chunker
            reload(src.ingestion.chunker)
            from src.ingestion.chunker import chunk_file

            with pytest.raises(ImportError, match="pymupdf"):
                chunk_file(str(f))
        finally:
            builtins.__import__ = orig_import
            import src.ingestion.chunker
            reload(src.ingestion.chunker)

    def test_docx_raises_import_error_if_python_docx_not_installed(self, tmp_path):
        f = tmp_path / "doc.docx"

        import builtins
        orig_import = builtins.__import__

        def _fake_import(name, *args, **kwargs):
            if name == "docx":
                raise ImportError()
            return orig_import(name, *args, **kwargs)

        builtins.__import__ = _fake_import
        try:
            from importlib import reload

            import src.ingestion.chunker
            reload(src.ingestion.chunker)
            from src.ingestion.chunker import chunk_file

            with pytest.raises(ImportError, match="python-docx"):
                chunk_file(str(f))
        finally:
            builtins.__import__ = orig_import
            import src.ingestion.chunker
            reload(src.ingestion.chunker)
