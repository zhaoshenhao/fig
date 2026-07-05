import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.rag.qdrant import QdrantSearch


def _get_client(args) -> QdrantSearch:
    return QdrantSearch(
        host=args.qdrant_host,
        port=args.qdrant_port,
    )


def cmd_list(args):
    qdrant = _get_client(args)
    names = qdrant.list_collections()
    if names:
        for n in names:
            print(n)
    else:
        print("(no collections)")


def cmd_info(args):
    qdrant = _get_client(args)
    import json
    info = qdrant.collection_info(args.collection)
    print(json.dumps(info, indent=2, ensure_ascii=False, default=str))


def cmd_delete(args):
    qdrant = _get_client(args)
    if not args.yes:
        answer = input(f"Delete collection '{args.collection}'? [y/N]: ")
        if answer.lower() not in ("y", "yes"):
            print("aborted.")
            return
    qdrant.delete_collection(args.collection)
    print(f"Deleted: {args.collection}")


def cmd_browse(args):
    qdrant = _get_client(args)
    offset = args.offset or 0
    while True:
        results, next_offset = qdrant.scroll(args.collection, limit=args.limit, offset=offset)
        if not results:
            print("(end)")
            break
        for r in results:
            payload = r.get("payload", {})
            source = payload.get("source", "")
            text = payload.get("text", "")[:80]
            print(f"  id={r['id']}  source={source}  text={text}")
        if next_offset is None:
            break
        if not args.all:
            break
        offset = next_offset


def cmd_search(args):
    qdrant = _get_client(args)
    from src.llm.client import LLMClient

    ollama_url = args.ollama_url
    embed_model = args.embed_model
    client = LLMClient(base_url=ollama_url)
    vectors = client.embed(embed_model, [args.query])
    vector = vectors[0]

    results = qdrant.search(
        args.collection, vector, query_text=args.query,
        limit=args.limit, score_threshold=args.score_threshold,
    )
    for r in results:
        payload = r.get("payload", {})
        text = payload.get("text", "")[:100]
        print(f"  score={r['score']:.4f}  source={payload.get('source', '')}")
        print(f"  {text}\n")


def cmd_count(args):
    qdrant = _get_client(args)
    n = qdrant.count(args.collection)
    print(f"{args.collection}: {n} points")


def main():
    parser = argparse.ArgumentParser(description="Knowledge base management CLI")
    parser.add_argument(
        "--qdrant-host", default=os.environ.get("QDRANT_HOST", "localhost"),
        help="Qdrant host",
    )
    parser.add_argument(
        "--qdrant-port", type=int, default=int(os.environ.get("QDRANT_PORT", "6334")),
        help="Qdrant gRPC port",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List all collections")

    p_info = sub.add_parser("info", help="Show collection details")
    p_info.add_argument("collection")

    p_delete = sub.add_parser("delete", help="Delete a collection")
    p_delete.add_argument("collection")
    p_delete.add_argument("--yes", "-y", action="store_true", help="Skip confirmation")

    p_browse = sub.add_parser("browse", help="Browse collection points")
    p_browse.add_argument("collection")
    p_browse.add_argument("--limit", type=int, default=20)
    p_browse.add_argument("--offset", type=int, default=0)
    p_browse.add_argument("--all", "-a", action="store_true", help="Browse all pages")

    p_search = sub.add_parser("search", help="Search a collection")
    p_search.add_argument("collection")
    p_search.add_argument("query")
    p_search.add_argument(
        "--ollama-url",
        default=os.environ.get("OLLAMA_HOST", "http://localhost:11434/v1"),
    )
    p_search.add_argument(
        "--embed-model",
        default=os.environ.get("EMBED_MODEL", "nomic-embed-text"),
    )
    p_search.add_argument("--limit", type=int, default=5)
    p_search.add_argument("--score-threshold", type=float, default=None)

    p_count = sub.add_parser("count", help="Count points in a collection")
    p_count.add_argument("collection")

    args = parser.parse_args()

    commands = {
        "list": cmd_list,
        "info": cmd_info,
        "delete": cmd_delete,
        "browse": cmd_browse,
        "search": cmd_search,
        "count": cmd_count,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
