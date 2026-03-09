#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional, Tuple

import chromadb

from acquittify.config import CHROMA_COLLECTION
from acquittify_taxonomy import TAXONOMY_SET


@dataclass
class LengthStats:
    minimum: int
    maximum: int
    average: float
    median: float
    p90: float
    p95: float


def _percentile(values: List[int], pct: float) -> float:
    if not values:
        return 0.0
    values_sorted = sorted(values)
    idx = int(round((pct / 100.0) * (len(values_sorted) - 1)))
    return float(values_sorted[idx])


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


def _get_collection(chroma_dir: str, name: Optional[str]) -> Any:
    client = chromadb.PersistentClient(path=chroma_dir)
    return client.get_or_create_collection(name=name or CHROMA_COLLECTION)


def _length_histogram(lengths: Iterable[int]) -> Dict[str, int]:
    bins = [0, 200, 400, 600, 800, 1000, 1200, 1500, 2000]
    counts = Counter()
    for length in lengths:
        placed = False
        for i in range(len(bins) - 1):
            low = bins[i]
            high = bins[i + 1]
            if low <= length < high:
                counts[f"{low}-{high}"] += 1
                placed = True
                break
        if not placed:
            counts[">=2000"] += 1
    return dict(counts)


def _metadata_missing_counter(meta: Dict[str, Any], keys: Iterable[str]) -> Counter:
    missing = Counter()
    for key in keys:
        value = meta.get(key)
        if value is None:
            missing[key] += 1
        elif isinstance(value, str) and not value.strip():
            missing[key] += 1
    return missing


def _iter_collection(
    collection: Any,
    sample_limit: int,
    batch_size: int,
) -> Iterable[Tuple[List[str], List[Dict[str, Any]], List[str]]]:
    total = collection.count()
    sample_size = min(sample_limit, total)
    for offset in range(0, sample_size, batch_size):
        limit = min(batch_size, sample_size - offset)
        res = collection.get(
            limit=limit,
            offset=offset,
            include=["metadatas", "documents"],
        )
        yield (
            res.get("ids") or [],
            res.get("metadatas") or [],
            res.get("documents") or [],
        )


def audit_chroma(
    chroma_dir: str,
    collection_name: Optional[str],
    sample_limit: int,
    batch_size: int,
) -> Dict[str, Any]:
    collection = _get_collection(chroma_dir, collection_name)
    total = collection.count()
    sample_size = min(sample_limit, total)

    missing = Counter()
    source_types = Counter()
    document_types = Counter()
    taxonomy_codes: set[str] = set()
    lengths: List[int] = []
    hist = defaultdict(Counter)

    keys_to_track = [
        "title",
        "path",
        "source_type",
        "document_type",
        "doc_id",
        "chunk_index",
        "taxonomy",
        "citations",
        "statutes",
        "rules",
        "citation_count",
        "statute_count",
        "rule_count",
        "authority_weight",
        "court",
        "year",
        "date_filed",
        "citation",
    ]

    for _, metas, docs in _iter_collection(collection, sample_limit, batch_size):
        for idx, meta in enumerate(metas):
            if not isinstance(meta, dict):
                meta = {}
            missing.update(_metadata_missing_counter(meta, keys_to_track))

            source_types[meta.get("source_type") or "UNKNOWN"] += 1
            document_types[meta.get("document_type") or "UNKNOWN"] += 1

            codes = _parse_taxonomy(meta)
            for code in codes:
                taxonomy_codes.add(code)

            for key in ("citation_count", "statute_count", "rule_count", "authority_weight", "year"):
                value = meta.get(key)
                if value is None:
                    continue
                try:
                    hist[key][int(value)] += 1
                except Exception:
                    hist[key][str(value)] += 1

            doc = docs[idx] if idx < len(docs) else ""
            if doc:
                lengths.append(len(doc))

    length_stats = LengthStats(
        minimum=min(lengths) if lengths else 0,
        maximum=max(lengths) if lengths else 0,
        average=mean(lengths) if lengths else 0.0,
        median=_percentile(lengths, 50.0),
        p90=_percentile(lengths, 90.0),
        p95=_percentile(lengths, 95.0),
    )

    coverage = {
        "total_nodes": len(TAXONOMY_SET),
        "covered_nodes": len(taxonomy_codes),
        "coverage_ratio": (len(taxonomy_codes) / len(TAXONOMY_SET)) if TAXONOMY_SET else 0.0,
    }

    return {
        "collection": collection.name if hasattr(collection, "name") else collection_name,
        "total": total,
        "sample_size": sample_size,
        "missing_metadata": dict(missing),
        "source_type_distribution": dict(source_types),
        "document_type_distribution": dict(document_types),
        "length_stats": {
            "min": length_stats.minimum,
            "max": length_stats.maximum,
            "avg": round(length_stats.average, 2),
            "median": length_stats.median,
            "p90": length_stats.p90,
            "p95": length_stats.p95,
            "histogram": _length_histogram(lengths),
        },
        "histograms": {key: dict(counter) for key, counter in hist.items()},
        "taxonomy_coverage": coverage,
        "taxonomy_codes_sampled": sorted(list(taxonomy_codes))[:200],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a Chroma audit snapshot report.")
    parser.add_argument("--chroma-dir", default=os.getenv("CHROMA_DIR", "Corpus/Chroma"))
    parser.add_argument("--collection", default=None)
    parser.add_argument("--sample-limit", type=int, default=3000)
    parser.add_argument("--batch-size", type=int, default=250)
    parser.add_argument("--report", default="eval/chroma_audit.json")
    args = parser.parse_args()

    report = audit_chroma(
        chroma_dir=args.chroma_dir,
        collection_name=args.collection,
        sample_limit=args.sample_limit,
        batch_size=args.batch_size,
    )

    out_path = Path(args.report)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
