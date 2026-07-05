import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.ingestion.builder import build_directory
from src.ingestion.chunker import SUPPORTED_EXTENSIONS
from src.llm.client import LLMClient
from src.rag.qdrant import QdrantSearch


def main():
    parser = argparse.ArgumentParser(
        description="Document ingestion CLI — build collections from directories"
    )
    parser.add_argument(
        "--dir", default=os.environ.get("BUILD_DIR", "data/documents"),
        help="Source directory path (default: data/documents)",
    )
    parser.add_argument(
        "--collection", default=os.environ.get("BUILD_COLLECTION", "default"),
        help="Target Qdrant collection name (default: default)",
    )
    parser.add_argument(
        "--chunk-size", type=int, default=int(os.environ.get("CHUNK_SIZE", "800")),
        help="Chunk size in characters (default: 800)",
    )
    parser.add_argument(
        "--chunk-overlap", type=int, default=128,
        help="Chunk overlap in characters (default: 128)",
    )
    parser.add_argument(
        "--qdrant-host", default=os.environ.get("QDRANT_HOST", "localhost"),
        help="Qdrant host (default: localhost)",
    )
    parser.add_argument(
        "--qdrant-port", type=int, default=int(os.environ.get("QDRANT_PORT", "6334")),
        help="Qdrant gRPC port (default: 6334)",
    )
    parser.add_argument(
        "--ollama-url", default=os.environ.get("OLLAMA_HOST", "http://localhost:11434/v1"),
        help="Ollama base URL (default: http://localhost:11434/v1)",
    )
    parser.add_argument(
        "--embed-model", default=os.environ.get("EMBED_MODEL", "nomic-embed-text"),
        help="Embedding model name (default: nomic-embed-text)",
    )
    parser.add_argument(
        "--extensions", default="",
        help="Comma-separated file extensions (default: auto-detect all supported)",
    )
    args = parser.parse_args()

    print(f"Qdrant: {args.qdrant_host}:{args.qdrant_port}")
    print(f"Ollama: {args.ollama_url}  model: {args.embed_model}")
    print(f"Source: {args.dir} -> collection: {args.collection}")
    print(f"Chunk size: {args.chunk_size}, overlap: {args.chunk_overlap}")

    qdrant = QdrantSearch(host=args.qdrant_host, port=args.qdrant_port)
    client = LLMClient(base_url=args.ollama_url)

    if args.extensions.strip():
        extensions = tuple(
            ext.strip() for ext in args.extensions.split(",") if ext.strip()
        )
    else:
        extensions = None  # auto-detect all supported
    print(f"Extensions: {extensions or SUPPORTED_EXTENSIONS}")

    count = build_directory(
        args.dir, args.collection, qdrant, client, args.embed_model,
        chunk_size=args.chunk_size, chunk_overlap=args.chunk_overlap,
        extensions=extensions,
    )

    print(f"Done. {count} chunks upserted to '{args.collection}'.")


if __name__ == "__main__":
    main()
