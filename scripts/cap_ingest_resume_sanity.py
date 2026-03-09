#!/usr/bin/env python3
"""Sanity-check resume log skipping for CAP ingest."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.ingest_cap_jsonl import _doc_id, _iter_records, _iter_shards, ingest_shards


def main() -> None:
    base = Path("acquittify-data")
    shards_dir = base / "ingest" / "cases"
    if not shards_dir.exists():
        raise SystemExit("missing ingest/cases; run normalize_cap.py first")

    first_shard = next(_iter_shards(shards_dir), None)
    if first_shard is None:
        raise SystemExit("no shards found")

    first_record = next(_iter_records(first_shard), None)
    if first_record is None:
        raise SystemExit("no records in first shard")

    doc_id = _doc_id(first_record)
    resume_log = Path("reports") / "cap_ingest_resume_sanity.jsonl"
    resume_log.parent.mkdir(parents=True, exist_ok=True)
    resume_log.write_text(json.dumps({"doc_id": doc_id}) + "\n", encoding="utf-8")

    summary = ingest_shards(
        shards_dir,
        Path("Corpus/Chroma"),
        limit=1,
        resume_log=resume_log,
    )

    if summary.get("skipped_seen") != 1:
        raise SystemExit(f"expected skipped_seen=1, got {summary}")

    print("ok", json.dumps(summary))


if __name__ == "__main__":
    main()
