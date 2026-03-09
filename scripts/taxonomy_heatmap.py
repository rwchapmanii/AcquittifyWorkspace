#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

import chromadb

from acquittify.config import CHROMA_COLLECTION


def _parse_taxonomy(meta: Dict[str, Any]) -> List[str]:
    raw = meta.get("taxonomy")
    if not raw:
        return []
    if isinstance(raw, dict):
        parsed = raw
    elif isinstance(raw, str):
        raw_str = raw.strip()
        if not raw_str or raw_str in {"{}", "[]", "null"}:
            return []
        try:
            parsed = json.loads(raw_str)
        except Exception:
            return []
    else:
        return []

    codes: List[str] = []
    if isinstance(parsed, dict):
        for value in parsed.values():
            if isinstance(value, list):
                codes.extend([str(item) for item in value if item])
    return codes


def _facet_and_bucket(code: str) -> tuple[str, str]:
    parts = code.split(".")
    if len(parts) < 3:
        return ("UNKNOWN", "UNKNOWN")
    facet = parts[1]
    bucket = parts[2]
    return (facet, bucket)


def _color_scale(value: float) -> str:
    # value expected 0..1
    hue = 210  # blue
    saturation = 60
    lightness = int(95 - (value * 55))  # 95 -> 40
    return f"hsl({hue} {saturation}% {lightness}%)"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate taxonomy heatmap (facet x top-level bucket).")
    parser.add_argument("--chroma-dir", default=os.getenv("CHROMA_DIR", "Corpus/Chroma"))
    parser.add_argument("--collection", default=None)
    parser.add_argument("--sample-limit", type=int, default=5000)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--output", default="eval/taxonomy_heatmap.html")
    parser.add_argument("--json", default="eval/taxonomy_heatmap.json")
    args = parser.parse_args()

    client = chromadb.PersistentClient(path=args.chroma_dir)
    collection = client.get_or_create_collection(args.collection or CHROMA_COLLECTION)

    total = collection.count()
    sample_size = min(args.sample_limit, total)

    facet_bucket_counts: Dict[str, Counter] = defaultdict(Counter)
    facet_counts = Counter()
    bucket_counts = Counter()

    for offset in range(0, sample_size, args.batch_size):
        limit = min(args.batch_size, sample_size - offset)
        res = collection.get(limit=limit, offset=offset, include=["metadatas"])
        metas = res.get("metadatas") or []
        for meta in metas:
            if not isinstance(meta, dict):
                continue
            codes = _parse_taxonomy(meta)
            if not codes:
                continue
            for code in codes:
                facet, bucket = _facet_and_bucket(code)
                facet_bucket_counts[facet][bucket] += 1
                facet_counts[facet] += 1
                bucket_counts[bucket] += 1

    facets = sorted(facet_bucket_counts.keys())
    buckets = sorted(bucket_counts.keys())

    max_cell = 0
    for facet in facets:
        for bucket in buckets:
            max_cell = max(max_cell, facet_bucket_counts[facet][bucket])

    rows = []
    for facet in facets:
        row = []
        for bucket in buckets:
            row.append(facet_bucket_counts[facet][bucket])
        rows.append(row)

    # Write JSON summary
    json_path = Path(args.json)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(
            {
                "sample_size": sample_size,
                "total": total,
                "facets": facets,
                "buckets": buckets,
                "matrix": rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # Build HTML
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    header_cells = "".join(f"<th>{bucket}</th>" for bucket in buckets)
    body_rows = []
    for f_idx, facet in enumerate(facets):
        cells = [f"<td class='facet'>{facet}</td>"]
        for b_idx, bucket in enumerate(buckets):
            value = rows[f_idx][b_idx]
            intensity = (value / max_cell) if max_cell else 0
            color = _color_scale(intensity)
            cells.append(
                f"<td style='background:{color}' title='{facet} / {bucket}: {value}'>"
                f"{value}</td>"
            )
        body_rows.append("<tr>" + "".join(cells) + "</tr>")

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Taxonomy Heatmap</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #111; }}
    h1 {{ font-size: 20px; }}
    .meta {{ color: #555; margin-bottom: 12px; }}
    table {{ border-collapse: collapse; width: 100%; table-layout: fixed; }}
    th, td {{ border: 1px solid #ddd; padding: 6px; text-align: center; font-size: 12px; }}
    th {{ background: #f5f5f5; position: sticky; top: 0; z-index: 1; }}
    td.facet {{ text-align: left; font-weight: 600; background: #fafafa; position: sticky; left: 0; z-index: 1; }}
  </style>
</head>
<body>
  <h1>Taxonomy Heatmap (Facet x Top-Level Bucket)</h1>
  <div class="meta">Sample size: {sample_size} / {total}</div>
  <table>
    <thead>
      <tr>
        <th>Facet</th>
        {header_cells}
      </tr>
    </thead>
    <tbody>
      {''.join(body_rows)}
    </tbody>
  </table>
</body>
</html>"""

    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote {out_path} and {json_path}")


if __name__ == "__main__":
    main()
