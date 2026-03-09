#!/usr/bin/env python3
"""Sanity-check CourtListener opinion caching and hashing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ingestion_agent.config import Settings
from ingestion_agent.sources.courtlistener import CourtListenerClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate opinion fetch caching and hashing.")
    parser.add_argument("--opinion-id", required=True, help="Opinion ID to fetch")
    args = parser.parse_args()

    settings = Settings()
    client = CourtListenerClient(settings)

    cache_path = client.cache_path_for_opinion(args.opinion_id)
    cache_before = cache_path.exists()

    record = client.fetch_opinion(args.opinion_id)
    cache_after = cache_path.exists()

    cached_hash = None
    if cache_after:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        cached_hash = cached.get("text_hash")

    current_hash = client.opinion_text_hash(record)

    print("cache_before=", cache_before)
    print("cache_after=", cache_after)
    print("hash_matches=", cached_hash == current_hash)
    print("cache_path=", cache_path)


if __name__ == "__main__":
    main()
