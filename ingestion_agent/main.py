"""Main entry point for the ingestion pipeline."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Tuple

from ingestion_agent.config import Settings
from acquittify.ingest.unified import ingest_courtlistener
from acquittify.paths import CHROMA_DIR


def _load_state(state_path: str) -> dict:
    path = Path(state_path)
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _save_state(state_path: str, state: dict) -> None:
    path = Path(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))


def run_ingestion(since: str | None, max_pages: int, settings: Settings) -> None:
    print("ingestion_agent is deprecated; using unified ingestion pipeline.")
    ingest_courtlistener(
        chroma_dir=CHROMA_DIR,
        since=since,
        max_pages=max_pages,
        use_taxonomy=True,
    )
    now_iso = datetime.utcnow().date().isoformat()
    _save_state(settings.state_path, {"last_run": now_iso})


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the legal ingestion pipeline.")
    parser.add_argument("--since", help="ISO date (YYYY-MM-DD) to start from")
    parser.add_argument("--max-pages", type=int, default=1, help="Max pages per endpoint")
    parser.add_argument("--use-state", action="store_true", help="Use last run date from state")
    return parser


def main() -> None:
    settings = Settings()
    parser = build_arg_parser()
    args = parser.parse_args()

    since = args.since
    if args.use_state:
        state = _load_state(settings.state_path)
        since = state.get("last_run") or since

    run_ingestion(since=since, max_pages=args.max_pages, settings=settings)


if __name__ == "__main__":
    main()
