#!/usr/bin/env python3
"""Background worker to fill missing CAP case summaries using LLM."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import chromadb
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from acquittify.config import CHROMA_COLLECTION
from acquittify.chroma_utils import get_or_create_collection


def _load_index(path: Path) -> List[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _write_index(path: Path, rows: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".jsonl.tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp_path.replace(path)


def _fetch_case_text(collection, doc_id: str, max_chars: int = 4000) -> str:
    try:
        res = collection.get(where={"doc_id": doc_id}, include=["documents", "metadatas"])
    except Exception:
        return ""
    docs = res.get("documents") or []
    if not docs:
        return ""
    # take the longest chunks first
    ordered = sorted(docs, key=lambda d: len(d or ""), reverse=True)
    combined = " ".join((d or "") for d in ordered)
    combined = " ".join(combined.split())
    return combined[:max_chars]


def _llm_summary(text: str, meta: dict, model: str, url: str, max_chars: int) -> Optional[str]:
    if not text:
        return None
    prompt = f"""
Summarize this case for a case-law library.
Return JSON with keys: issue, holding, key_facts, disposition.
Be concise and factual. If unknown, return "Unknown" for that field.

Case name: {meta.get("case_name") or meta.get("title") or "Unknown"}
Court: {meta.get("court") or "Unknown"}
Decision date: {meta.get("decision_date") or meta.get("date") or "Unknown"}
Citation: {meta.get("document_citation") or "Unknown"}

Text excerpt:
{text[:max_chars]}
"""
    try:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "Return only valid JSON. No prose."},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {"temperature": 0},
        }
        response = requests.post(url, json=payload, timeout=90)
        response.raise_for_status()
        data = response.json()
        content = data.get("message", {}).get("content", "{}").strip()
        parsed = json.loads(content)
        issue = parsed.get("issue") or "Unknown"
        holding = parsed.get("holding") or "Unknown"
        key_facts = parsed.get("key_facts") or "Unknown"
        disposition = parsed.get("disposition") or "Unknown"
        return f"Issue: {issue}\nHolding: {holding}\nKey Facts: {key_facts}\nDisposition: {disposition}"
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate missing CAP case summaries in background.")
    parser.add_argument("--index", default="reports/cap_case_index.jsonl", help="Case index JSONL")
    parser.add_argument("--chroma-dir", default="Corpus/Chroma", help="Chroma directory")
    parser.add_argument("--collection", default=CHROMA_COLLECTION, help="Chroma collection")
    parser.add_argument("--limit", type=int, default=None, help="Limit cases processed")
    parser.add_argument(
        "--only-missing",
        action="store_true",
        help="Only generate summaries where missing or non-LLM",
    )
    parser.add_argument(
        "--summary-model",
        default=os.getenv("ACQUITTIFY_LIBRARY_SUMMARY_MODEL", "acquittify-qwen"),
        help="LLM model for summaries",
    )
    parser.add_argument(
        "--summary-url",
        default=os.getenv("ACQUITTIFY_LIBRARY_SUMMARY_URL", "http://localhost:11434/api/chat"),
        help="LLM URL",
    )
    parser.add_argument("--summary-max-chars", type=int, default=4000, help="Max chars for summary prompt")
    args = parser.parse_args()

    index_path = Path(args.index)
    rows = _load_index(index_path)
    if not rows:
        print("No case index rows found.")
        return 0

    client = chromadb.PersistentClient(path=str(args.chroma_dir))
    collection = get_or_create_collection(client, name=args.collection)

    updated = 0
    now = datetime.now(timezone.utc).isoformat()
    for row in rows:
        if args.limit is not None and updated >= args.limit:
            break
        summary = row.get("summary")
        method = row.get("summary_method")
        if args.only_missing and summary and method == "llm":
            continue
        doc_id = row.get("doc_id")
        if not doc_id:
            continue
        text = _fetch_case_text(collection, doc_id, max_chars=args.summary_max_chars)
        llm_summary = _llm_summary(text, row, args.summary_model, args.summary_url, args.summary_max_chars)
        if not llm_summary:
            continue
        row["summary"] = llm_summary
        row["summary_method"] = "llm"
        row["summary_updated_at"] = now
        updated += 1

    if updated:
        _write_index(index_path, rows)
    print(json.dumps({"updated": updated, "total": len(rows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
