#!/usr/bin/env python3
"""Build a reranker dataset from QA eval + Chroma retrieval results."""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import chromadb
from chromadb.config import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from acquittify.config import CHROMA_COLLECTION
from acquittify.chroma_utils import get_or_create_collection
from acquittify_query import classify_intent, expand_query
from acquittify_taxonomy import TAXONOMY_SET
from acquittify_retriever import retrieve

DEFAULT_EVAL = PROJECT_ROOT / "eval" / "qa_eval_expanded.jsonl"
DEFAULT_CHROMA_DIR = PROJECT_ROOT / "Corpus" / "Chroma"
DEFAULT_OUT_DIR = PROJECT_ROOT / "finetune" / "rag" / "data"


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


def _create_client(chroma_dir: Path):
    try:
        return chromadb.PersistentClient(path=str(chroma_dir))
    except Exception:
        try:
            settings = Settings(persist_directory=str(chroma_dir), anonymized_telemetry=False)
            return chromadb.Client(settings)
        except Exception:
            return chromadb.Client()


def _get_chunk_by_id(collection, chunk_id: str) -> Tuple[str | None, Dict[str, Any] | None]:
    try:
        result = collection.get(ids=[chunk_id], include=["documents", "metadatas"])
    except Exception:
        return None, None
    docs = result.get("documents") or []
    metas = result.get("metadatas") or []
    doc = docs[0] if docs else None
    meta = metas[0] if metas else None
    return doc, meta


def _build_examples(
    row: Dict[str, Any],
    collection,
    chroma_dir: Path,
    top_k: int,
    negatives_per_query: int,
) -> List[Dict[str, Any]]:
    question = (row.get("question") or "").strip()
    gold_id = row.get("gold_chunk_id")
    if not question or not gold_id:
        return []

    pos_text, _ = _get_chunk_by_id(collection, str(gold_id))
    if not pos_text:
        return []

    intent = classify_intent(question)
    expanded = expand_query(question, intent)
    legal_area = _select_legal_area(row.get("taxonomy"))

    results = retrieve(query=expanded, legal_area=legal_area, k=top_k, chroma_dir=chroma_dir)

    negatives: List[Dict[str, Any]] = []
    seen_texts = {pos_text}
    for result in results:
        doc_id = result.get("id")
        if doc_id and str(doc_id) == str(gold_id):
            continue
        text = result.get("text") or ""
        if not text or text in seen_texts:
            continue
        seen_texts.add(text)
        negatives.append({"doc_id": doc_id, "text": text})
        if len(negatives) >= negatives_per_query:
            break

    if not negatives:
        return []

    examples: List[Dict[str, Any]] = []
    base = {
        "qid": row.get("id"),
        "query": question,
        "expanded_query": expanded,
        "legal_area": legal_area,
    }
    examples.append({**base, "doc": pos_text, "doc_id": str(gold_id), "label": 1})
    for neg in negatives:
        examples.append({**base, "doc": neg["text"], "doc_id": neg.get("doc_id"), "label": 0})
    return examples


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build reranker dataset from QA eval JSONL.")
    parser.add_argument("--eval", default=str(DEFAULT_EVAL), help="QA eval JSONL input")
    parser.add_argument("--chroma-dir", default=str(DEFAULT_CHROMA_DIR), help="Chroma directory")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Output directory")
    parser.add_argument("--top-k", type=int, default=20, help="Top-k retrieval results to consider")
    parser.add_argument("--negatives", type=int, default=4, help="Negatives per query")
    parser.add_argument("--val-ratio", type=float, default=0.1, help="Validation ratio")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    eval_path = Path(args.eval)
    if not eval_path.exists():
        raise SystemExit(f"Eval file not found: {eval_path}")

    rows = _load_jsonl(eval_path)
    if not rows:
        raise SystemExit("Eval file is empty or invalid.")

    chroma_dir = Path(args.chroma_dir)
    client = _create_client(chroma_dir)
    collection = get_or_create_collection(client, name=CHROMA_COLLECTION)

    by_qid: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        examples = _build_examples(
            row,
            collection,
            chroma_dir,
            top_k=args.top_k,
            negatives_per_query=args.negatives,
        )
        if not examples:
            continue
        qid = row.get("id") or f"row_{len(by_qid)}"
        by_qid[qid] = examples

    if not by_qid:
        raise SystemExit("No reranker examples built. Check gold_chunk_id coverage.")

    rng = random.Random(args.seed)
    qids = list(by_qid.keys())
    rng.shuffle(qids)
    val_count = int(len(qids) * args.val_ratio)
    val_qids = set(qids[:val_count])

    train_rows: List[Dict[str, Any]] = []
    val_rows: List[Dict[str, Any]] = []
    for qid, examples in by_qid.items():
        if qid in val_qids:
            val_rows.extend(examples)
        else:
            train_rows.extend(examples)

    out_dir = Path(args.out_dir)
    _write_jsonl(out_dir / "reranker_train.jsonl", train_rows)
    _write_jsonl(out_dir / "reranker_val.jsonl", val_rows)

    print(
        f"Wrote {len(train_rows)} train and {len(val_rows)} val examples to {out_dir}"
    )


if __name__ == "__main__":
    main()
