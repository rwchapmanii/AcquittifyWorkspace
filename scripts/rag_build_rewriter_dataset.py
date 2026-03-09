#!/usr/bin/env python3
"""Build a query-rewriter fine-tune dataset from a QA eval JSONL."""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from acquittify_query import classify_intent, expand_query
from acquittify_taxonomy import TAXONOMY_SET

DEFAULT_EVAL = PROJECT_ROOT / "eval" / "qa_eval_expanded.jsonl"
DEFAULT_OUT_DIR = PROJECT_ROOT / "finetune" / "rag" / "data"

SYSTEM_PROMPT = (
    "You are a search query rewriter for legal retrieval. "
    "Return ONLY JSON with keys: expanded_query, legal_area. "
    "Use the provided question, intent, and taxonomy to expand the query and choose the best legal_area. "
    "If uncertain, use 'General Federal Criminal Law'."
)


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def _select_legal_area(raw_taxonomy: Any) -> str:
    if raw_taxonomy is None:
        return "General Federal Criminal Law"
    candidates: List[str] = []
    if isinstance(raw_taxonomy, str):
        text = raw_taxonomy.strip()
        if text:
            try:
                parsed = json.loads(text)
            except Exception:
                parsed = None
            if isinstance(parsed, dict):
                candidates.extend([str(k) for k in parsed.keys()])
                for val in parsed.values():
                    if isinstance(val, list):
                        candidates.extend([str(v) for v in val])
                    elif isinstance(val, str):
                        candidates.append(val)
            elif isinstance(parsed, list):
                candidates.extend([str(v) for v in parsed])
            else:
                candidates.append(text)
    elif isinstance(raw_taxonomy, list):
        candidates.extend([str(v) for v in raw_taxonomy])
    elif isinstance(raw_taxonomy, dict):
        candidates.extend([str(k) for k in raw_taxonomy.keys()])
        for val in raw_taxonomy.values():
            if isinstance(val, list):
                candidates.extend([str(v) for v in val])
            elif isinstance(val, str):
                candidates.append(val)

    for cand in candidates:
        cand = cand.strip()
        if cand in TAXONOMY_SET:
            return cand
    return "General Federal Criminal Law"


def _build_record(row: Dict[str, Any]) -> Dict[str, Any] | None:
    question = (row.get("question") or "").strip()
    if not question:
        return None
    intent = classify_intent(question)
    expanded = expand_query(question, intent)
    legal_area = _select_legal_area(row.get("taxonomy"))

    user = {
        "question": question,
        "intent": intent or "Unknown",
        "taxonomy": row.get("taxonomy") or "Unknown",
    }
    assistant = {
        "expanded_query": expanded,
        "legal_area": legal_area,
    }

    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            {"role": "assistant", "content": json.dumps(assistant, ensure_ascii=False)},
        ]
    }


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build query-rewriter dataset from QA eval JSONL.")
    parser.add_argument("--eval", default=str(DEFAULT_EVAL), help="QA eval JSONL input")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Output directory")
    parser.add_argument("--val-ratio", type=float, default=0.1, help="Validation ratio")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    eval_path = Path(args.eval)
    if not eval_path.exists():
        raise SystemExit(f"Eval file not found: {eval_path}")

    rows = _load_jsonl(eval_path)
    records: List[Dict[str, Any]] = []
    for row in rows:
        record = _build_record(row)
        if record:
            records.append(record)

    if not records:
        raise SystemExit("No records built from eval file.")

    rng = random.Random(args.seed)
    rng.shuffle(records)

    val_count = int(len(records) * args.val_ratio)
    val_records = records[:val_count]
    train_records = records[val_count:]

    out_dir = Path(args.out_dir)
    _write_jsonl(out_dir / "rewriter_train.jsonl", train_records)
    _write_jsonl(out_dir / "rewriter_val.jsonl", val_records)

    print(
        f"Wrote {len(train_records)} train and {len(val_records)} val records to {out_dir}"
    )


if __name__ == "__main__":
    main()
