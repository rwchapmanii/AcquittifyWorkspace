#!/usr/bin/env python3
"""Sanity-check CAP ingest loader on a small sample."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.ingest_cap_jsonl import ingest_shards


def main() -> None:
    base = Path("acquittify-data")
    sample_dir = base / "ingest" / "cases"
    if not sample_dir.exists():
        raise SystemExit("missing ingest/cases; run normalize_cap.py first")

    reports_dir = Path("reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    inspect_path = reports_dir / "cap_ingest_inspect_sample.jsonl"

    summary = ingest_shards(
        sample_dir,
        Path("Corpus/Chroma"),
        limit=1,
        inspect=True,
        inspect_records=1,
        inspect_chunks=1,
        inspect_output=inspect_path,
    )
    if summary.get("records") != 1:
        raise SystemExit(f"expected 1 record, got {summary}")
    if not inspect_path.exists() or inspect_path.stat().st_size == 0:
        raise SystemExit("inspect output was not created")
    print("ok", json.dumps(summary))


if __name__ == "__main__":
    main()
