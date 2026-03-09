#!/usr/bin/env python3
"""Render a live-updating CAP ingest progress log as Markdown."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def _read_last_records(path: Path, limit: int) -> list[dict]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    items: list[dict] = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return items


def _format_row(payload: dict) -> str:
    stage = payload.get("stage", "")
    records = payload.get("records", 0)
    chunks = payload.get("chunks", 0)
    skipped = payload.get("skipped", 0)
    skipped_nc = payload.get("skipped_non_criminal", 0)
    skipped_seen = payload.get("skipped_seen", 0)
    ts = payload.get("ts", 0)
    return f"| {stage} | {records} | {chunks} | {skipped} | {skipped_nc} | {skipped_seen} | {ts:.0f} |"


def _render_markdown(payloads: list[dict]) -> str:
    header = (
        "# CAP Ingest Progress\n\n"
        "| Stage | Records | Chunks | Skipped | Skipped non-criminal | Skipped seen | Timestamp |\n"
        "|---|---:|---:|---:|---:|---:|---:|\n"
    )
    rows = [
        _format_row(payload)
        for payload in payloads
        if isinstance(payload, dict)
    ]
    return header + "\n".join(rows) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Watch CAP ingest progress JSONL and render Markdown.")
    parser.add_argument(
        "--input",
        default="reports/ingest_CAP_progress.jsonl",
        help="Path to progress JSONL",
    )
    parser.add_argument(
        "--output",
        default="reports/ingest_CAP_progress.md",
        help="Path to output Markdown file",
    )
    parser.add_argument(
        "--tail",
        type=int,
        default=50,
        help="Number of recent entries to include",
    )
    parser.add_argument(
        "--watch",
        type=float,
        default=5.0,
        help="Seconds between refreshes",
    )

    args = parser.parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    while True:
        payloads = _read_last_records(input_path, args.tail)
        output_path.write_text(_render_markdown(payloads), encoding="utf-8")
        time.sleep(args.watch)


if __name__ == "__main__":
    raise SystemExit(main())
