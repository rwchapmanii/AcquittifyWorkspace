from __future__ import annotations

import argparse
import json

from .chat import answer
from .config import INDEX_INTERVAL, VAULT_PATH
from .indexer import build_index, manifest_stats, watch_index
from .searcher import search


def main() -> None:
    parser = argparse.ArgumentParser(description="Peregrine local agent")
    sub = parser.add_subparsers(dest="command")

    index_parser = sub.add_parser("index", help="Index the Obsidian vault")
    index_parser.add_argument("--limit", type=int, default=None, help="Limit files indexed")
    index_parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Rebuild the index from scratch",
    )

    watch_parser = sub.add_parser("watch", help="Continuously index the vault")
    watch_parser.add_argument(
        "--interval",
        type=int,
        default=INDEX_INTERVAL,
        help="Polling interval seconds",
    )

    search_parser = sub.add_parser("search", help="Search the vault")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--limit", type=int, default=5, help="Number of results")

    chat_parser = sub.add_parser("chat", help="Ask a question with RAG")
    chat_parser.add_argument("query", help="Question to answer")
    chat_parser.add_argument("--limit", type=int, default=5, help="Number of context chunks")

    status_parser = sub.add_parser("status", help="Show index status")

    args = parser.parse_args()

    if args.command == "index":
        print(f"Indexing vault at: {VAULT_PATH}")
        result = build_index(limit=args.limit, rebuild=args.rebuild)
        print(json.dumps(result, indent=2))
        return

    if args.command == "watch":
        print(f"Watching vault at: {VAULT_PATH} (interval {args.interval}s)")
        watch_index(interval=args.interval)
        return

    if args.command == "search":
        results = search(args.query, limit=args.limit)
        print(json.dumps(results, indent=2))
        return

    if args.command == "chat":
        result = answer(args.query, limit=args.limit)
        print(json.dumps(result, indent=2))
        return

    if args.command == "status":
        print(json.dumps(manifest_stats(), indent=2))
        return

    parser.print_help()


if __name__ == "__main__":
    main()
