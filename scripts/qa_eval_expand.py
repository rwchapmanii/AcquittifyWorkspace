#!/usr/bin/env python3
"""Expand an existing QA eval set by generating additional items.

This script reuses the QA generation logic from scripts/qa_eval_generate.py,
while avoiding duplicate gold_chunk_id values in the output.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import qa_eval_generate as qg
from acquittify.config import CHUNK_MIN_CHARS

DEFAULT_CHROMA_DIR = PROJECT_ROOT / "Corpus" / "Chroma"
DEFAULT_EXISTING = PROJECT_ROOT / "eval" / "qa_eval.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "eval" / "qa_eval_expanded.jsonl"


def _load_existing(path: Path) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if not path.exists():
        return items
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except Exception:
                continue
    return items


def _existing_ids(items: List[Dict[str, Any]]) -> Set[str]:
    used = set()
    for item in items:
        chunk_id = item.get("gold_chunk_id")
        if chunk_id:
            used.add(str(chunk_id))
    return used


def _collect_chunks(chroma_dir: Path):
    collection = qg._load_collection(chroma_dir)
    ids, docs, metas = qg._collect_chunks(collection)
    if not ids:
        ids, docs, metas = qg._collect_chunks_from_export(chroma_dir)
    if not ids:
        ids, docs, metas = qg._collect_chunks_from_documents(chroma_dir)
    if not ids:
        raise SystemExit("No chunks found in the Chroma collection or backups.")
    return ids, docs, metas


def _generate_records(
    *,
    ids: List[str],
    docs: List[str],
    metas: List[dict],
    used_chunk_ids: Set[str],
    needed: int,
    min_chars: int,
    rng: random.Random,
    source_type: Optional[str],
    use_ollama: bool,
    ollama_model: str,
    ollama_url: str,
    ollama_timeout: float,
    max_retries: int,
) -> List[Dict[str, Any]]:
    indices = list(range(len(ids)))
    rng.shuffle(indices)

    records: List[Dict[str, Any]] = []
    skipped = 0
    for idx in indices:
        if len(records) >= needed:
            break
        chunk_id = ids[idx]
        if str(chunk_id) in used_chunk_ids:
            skipped += 1
            continue
        chunk = docs[idx] if idx < len(docs) else ""
        meta = metas[idx] if idx < len(metas) else {}
        if not chunk or len(chunk) < min_chars:
            skipped += 1
            continue
        if source_type and isinstance(meta, dict):
            if (meta.get("source_type") or "") != source_type:
                skipped += 1
                continue

        detected = qg._detect_targets(chunk)
        required_targets = qg._select_required_targets(detected)
        if not required_targets:
            skipped += 1
            continue

        qa = None
        if use_ollama:
            for _ in range(max(1, max_retries)):
                qa = qg._call_ollama_structured(
                    chunk,
                    required_targets,
                    ollama_model,
                    ollama_url,
                    ollama_timeout,
                )
                if qa:
                    break
        if qa is None:
            qa = qg._heuristic_qa(chunk, required_targets)
        if qa is None:
            skipped += 1
            continue

        answer = qa.get("answer", "")
        if not qg._answer_in_chunk(answer, chunk):
            skipped += 1
            continue
        if len(answer.split()) > 30:
            skipped += 1
            continue
        if not qg._required_targets_satisfied(answer, required_targets):
            skipped += 1
            continue

        record = {
            "taxonomy": qg._taxonomy_value(meta),
            "question": qa.get("question"),
            "gold_answer": answer,
            "required_targets": required_targets,
            "gold_chunk_id": chunk_id,
            "gold_case_id": (meta.get("case_id") or meta.get("case") or meta.get("case_name"))
            if isinstance(meta, dict)
            else None,
            "metadata": qg._build_metadata(meta),
        }
        records.append(record)
        used_chunk_ids.add(str(chunk_id))

    if len(records) < needed:
        print(f"Warning: generated {len(records)} records (needed {needed}, skipped {skipped}).")
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Expand QA eval set to a target size.")
    parser.add_argument("--existing", default=str(DEFAULT_EXISTING), help="Existing QA eval JSONL")
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT), help="Output expanded JSONL")
    parser.add_argument("--target-total", type=int, default=2000, help="Total records after expansion")
    parser.add_argument("--additional", type=int, default=None, help="Generate this many new records")
    parser.add_argument("--chroma-dir", default=str(DEFAULT_CHROMA_DIR), help="Chroma directory")
    parser.add_argument("--min-chars", type=int, default=CHUNK_MIN_CHARS, help="Minimum characters in a chunk")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--source-type", default=None, help="Filter by metadata source_type")
    parser.add_argument("--ollama-url", default="http://localhost:11434/api/chat", help="Ollama chat endpoint")
    parser.add_argument("--ollama-model", default="qwen2.5:32b-instruct", help="Ollama model name")
    parser.add_argument("--ollama-timeout", type=float, default=30.0, help="Ollama request timeout seconds")
    parser.add_argument("--no-ollama", action="store_true", help="Disable Ollama and use heuristic QA")
    parser.add_argument("--max-retries", type=int, default=2, help="Max Ollama retries per chunk")
    args = parser.parse_args()

    existing_path = Path(args.existing)
    out_path = Path(args.out)

    existing = _load_existing(existing_path)
    used_chunk_ids = _existing_ids(existing)

    if args.additional is not None:
        needed = max(0, args.additional)
    else:
        needed = max(0, args.target_total - len(existing))

    if needed == 0 and existing:
        print("No new records needed; reindexing existing records.")
        all_records = existing
    else:
        chroma_dir = Path(args.chroma_dir)
        ids, docs, metas = _collect_chunks(chroma_dir)
        rng = random.Random(args.seed)
        new_records = _generate_records(
            ids=ids,
            docs=docs,
            metas=metas,
            used_chunk_ids=used_chunk_ids,
            needed=needed,
            min_chars=args.min_chars,
            rng=rng,
            source_type=args.source_type,
            use_ollama=not args.no_ollama,
            ollama_model=args.ollama_model,
            ollama_url=args.ollama_url,
            ollama_timeout=args.ollama_timeout,
            max_retries=args.max_retries,
        )
        all_records = existing + new_records

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        for idx, record in enumerate(all_records):
            record = dict(record)
            record["id"] = f"eval_{idx:05d}"
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"Wrote {len(all_records)} records to {out_path}")


if __name__ == "__main__":
    main()
