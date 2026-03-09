#!/usr/bin/env python3
"""Build ingestion SFT dataset from existing Chroma corpus.

Creates JSONL with messages: system + user(chunk) + assistant(JSON metadata).
Targets: citations, authority, taxonomy.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, List

import chromadb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from acquittify.config import CHROMA_COLLECTION
from acquittify.chroma_utils import get_or_create_collection

TARGET_KEYS = [
    "citations",
    "bluebook_citations",
    "statutes",
    "bluebook_statutes",
    "rules",
    "citation_count",
    "statute_count",
    "rule_count",
    "authority_weight",
    "authority_tier",
    "taxonomy",
]

SYSTEM_PROMPT = (
    "You are an ingestion metadata model for Acquittify. "
    "Given a document chunk, output ONLY valid JSON with the required keys. "
    "Do not add extra keys or prose. If a value is unknown, return an empty list, empty object, or 0 as appropriate. "
    "Required keys: citations, bluebook_citations, statutes, bluebook_statutes, rules, "
    "citation_count, statute_count, rule_count, authority_weight, authority_tier, taxonomy."
)


def _parse_jsonish(value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                return json.loads(stripped)
            except Exception:
                return value
    return value


def _normalize_label(meta: Dict[str, Any]) -> Dict[str, Any]:
    label: Dict[str, Any] = {}
    for key in TARGET_KEYS:
        val = meta.get(key)
        val = _parse_jsonish(val)
        if key in {"citations", "bluebook_citations", "statutes", "bluebook_statutes", "rules"}:
            if val is None:
                val = []
            if isinstance(val, str):
                val = [val] if val else []
        elif key in {"citation_count", "statute_count", "rule_count", "authority_weight"}:
            try:
                val = int(val) if val is not None else 0
            except Exception:
                val = 0
        elif key == "taxonomy":
            if val is None:
                val = {}
            if isinstance(val, str):
                try:
                    val = json.loads(val)
                except Exception:
                    val = {}
        elif key == "authority_tier":
            val = val or "Other"
        label[key] = val
    return label


def _load_collection(chroma_dir: Path):
    client = chromadb.PersistentClient(path=str(chroma_dir))
    return get_or_create_collection(client, name=CHROMA_COLLECTION)


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False))
            f.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ingestion dataset from Chroma corpus")
    parser.add_argument("--chroma-dir", type=Path, default=Path("Corpus/Chroma"))
    parser.add_argument("--out-dir", type=Path, default=Path("finetune/ingestion/data"))
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--shuffle", action="store_true")
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--val-ratio", type=float, default=0.1)
    parser.add_argument("--min-chars", type=int, default=200)
    args = parser.parse_args()

    collection = _load_collection(args.chroma_dir)
    res = collection.get(limit=args.limit, include=["documents", "metadatas"])
    docs = res.get("documents") or []
    metas = res.get("metadatas") or []
    ids = res.get("ids") or []

    rows: List[Dict[str, Any]] = []
    for doc, meta, doc_id in zip(docs, metas, ids):
        if not isinstance(doc, str):
            continue
        if len(doc.strip()) < args.min_chars:
            continue
        label = _normalize_label(meta or {})
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": doc},
            {"role": "assistant", "content": json.dumps(label, ensure_ascii=False)},
        ]
        rows.append({"messages": messages, "meta": {"id": doc_id}})

    if args.shuffle:
        random.seed(args.seed)
        random.shuffle(rows)

    total = len(rows)
    val_count = max(1, int(total * args.val_ratio)) if args.val_ratio > 0 else 0
    train_rows = rows[:-val_count] if val_count else rows
    val_rows = rows[-val_count:] if val_count else []

    out_dir = args.out_dir
    _write_jsonl(out_dir / "train.jsonl", train_rows)
    if val_rows:
        _write_jsonl(out_dir / "val.jsonl", val_rows)

    manifest = {
        "source": str(args.chroma_dir),
        "total_examples": total,
        "train_examples": len(train_rows),
        "val_examples": len(val_rows),
        "limit": args.limit,
        "val_ratio": args.val_ratio,
        "min_chars": args.min_chars,
        "target_keys": TARGET_KEYS,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
