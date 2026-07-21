from __future__ import annotations

import hashlib
import os
from collections.abc import Sequence
from pathlib import Path

from src.ingestion.chunker import SUPPORTED_EXTENSIONS, chunk_file
from src.llm.client import LLMClient
from src.rag.qdrant import QdrantSearch


EMBED_BATCH_SIZE = 4
EMBED_MAX_RETRIES = 3


def build_document(
    filepath: str | Path,
    collection: str,
    qdrant: QdrantSearch,
    embed_client: LLMClient,
    embed_model: str,
    chunk_size: int = 800,
    chunk_overlap: int = 64,
) -> int:
    filepath = Path(filepath)
    chunks = chunk_file(filepath, chunk_size, chunk_overlap)
    if not chunks:
        return 0

    vectors: list[list[float]] = []
    for i in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[i:i + EMBED_BATCH_SIZE]
        for attempt in range(EMBED_MAX_RETRIES):
            try:
                vectors.extend(embed_client.embed(embed_model, batch))
                break
            except Exception:
                if attempt == EMBED_MAX_RETRIES - 1:
                    raise
                import time
                time.sleep(2 * (attempt + 1))
                embed_client.close()
                embed_client._client = __import__('httpx2').Client(timeout=embed_client._timeout)

    source = str(filepath.name)
    points: list[dict] = []
    for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
        uid = _point_id(source, i)
        points.append({
            "id": uid,
            "vector": vector,
            "payload": {
                "text": chunk,
                "source": source,
                "chunk_index": i,
                "total_chunks": len(chunks),
            },
        })

    qdrant.ensure_collection(collection, vector_size=len(vectors[0]))
    qdrant.upsert(collection, points)

    return len(points)


def build_directory(
    directory: str | Path,
    collection: str,
    qdrant: QdrantSearch,
    embed_client: LLMClient,
    embed_model: str,
    chunk_size: int = 800,
    chunk_overlap: int = 64,
    extensions: Sequence[str] | None = None,
) -> int:
    if extensions is None:
        extensions = SUPPORTED_EXTENSIONS

    directory = Path(directory)
    if not directory.is_dir():
        raise NotADirectoryError(str(directory))

    total = 0
    for filepath in _iter_files(directory, extensions):
        total += build_document(
            filepath, collection, qdrant, embed_client, embed_model,
            chunk_size, chunk_overlap,
        )

    return total


def _point_id(source: str, index: int) -> int:
    raw = f"{source}:{index}".encode()
    return int(hashlib.md5(raw).hexdigest()[:12], 16)


def _iter_files(directory: Path, extensions: Sequence[str]):
    for filepath in sorted(directory.rglob("*")):
        if filepath.is_file() and filepath.suffix.lower() in extensions:
            yield filepath


def main():
    qdrant_host = os.environ.get("QDRANT_HOST", "localhost")
    qdrant_port = int(os.environ.get("QDRANT_PORT", "6334"))
    ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434/v1")
    embed_model = os.environ.get("EMBED_MODEL", "nomic-embed-text")
    target_dir = os.environ.get("BUILD_DIR", "data/documents")
    collection = os.environ.get("BUILD_COLLECTION", "default")
    chunk_size = int(os.environ.get("CHUNK_SIZE", "800"))
    extensions_env = os.environ.get("BUILD_EXTENSIONS", "")

    qdrant = QdrantSearch(host=qdrant_host, port=qdrant_port)
    client = LLMClient(base_url=ollama_host)
    extensions = tuple(extensions_env.split(",")) if extensions_env else None

    print(f"Qdrant: {qdrant_host}:{qdrant_port}")
    print(f"Embedding: {ollama_host} ({embed_model})")
    print(f"Source: {target_dir} -> collection: {collection}")
    print(f"Chunk size: {chunk_size}")

    count = build_directory(
        target_dir, collection, qdrant, client, embed_model,
        chunk_size=chunk_size, extensions=extensions,
    )
    print(f"Done. {count} chunks upserted.")


if __name__ == "__main__":
    main()
