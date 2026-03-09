import argparse
import json
import sys
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from acquittify_retriever import retrieve

DEFAULT_CHROMA_DIR = PROJECT_ROOT / "Corpus" / "Chroma"

_RULE_PATTERN = re.compile(r"\b(?:Fed\.\s+R\.|Rule\s+\d+|U\.S\.C\.|\b§\s*\d+)\b")
_DATE_PATTERN = re.compile(r"\b(19|20)\d{2}\b")
_ENTITY_PATTERN = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,}\b")


def _load_eval(path: Path) -> List[Dict[str, Any]]:
    items = []
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


def _normalize_chunk_index(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        return str(int(value))
    except Exception:
        return str(value)


def _is_hit(
    result: Dict[str, Any],
    target_path: Optional[str],
    target_chunk_index: Optional[str],
    target_id: Optional[str],
    relax_window: int,
    relax_document: bool,
) -> bool:
    if not result:
        return False
    path = result.get("path")
    idx = _normalize_chunk_index(result.get("chunk_index"))
    doc_id = result.get("id")
    if target_id and doc_id and str(doc_id) == str(target_id):
        return True
    if target_path and path and path == target_path and target_chunk_index is not None:
        if idx == target_chunk_index:
            return True
        try:
            if relax_window > 0:
                return abs(int(idx) - int(target_chunk_index)) <= relax_window
        except Exception:
            return False
    if relax_document and target_path and path and path == target_path:
        return True
    return False


def _rank_for_target(
    results: List[Dict[str, Any]],
    target_path: Optional[str],
    target_chunk_index: Optional[str],
    target_id: Optional[str],
    relax_window: int,
    relax_document: bool,
) -> Optional[int]:
    for i, result in enumerate(results, start=1):
        if _is_hit(result, target_path, target_chunk_index, target_id, relax_window, relax_document):
            return i
    return None


def _required_targets_satisfied(answer: str, required: Dict[str, bool]) -> bool:
    if required.get("must_include_rule_or_statute") and not _RULE_PATTERN.search(answer):
        return False
    if required.get("must_include_date") and not _DATE_PATTERN.search(answer):
        return False
    if required.get("must_include_entity") and not _ENTITY_PATTERN.search(answer):
        return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Run retrieval evaluation against a QA eval set.")
    parser.add_argument("--eval", default=str(PROJECT_ROOT / "eval" / "qa_eval.jsonl"), help="Eval JSONL path")
    parser.add_argument("--chroma-dir", default=str(DEFAULT_CHROMA_DIR), help="Path to Chroma directory")
    parser.add_argument("--k", type=int, default=5, help="Top-k retrieval")
    parser.add_argument("--report", default=str(PROJECT_ROOT / "eval" / "qa_eval_report.json"), help="Report JSON path")
    parser.add_argument("--relax-window", type=int, default=5, help="Allow chunk index +/- window match within same document")
    parser.add_argument("--relax-document", action="store_true", help="Count any hit in the same document as correct")
    args = parser.parse_args()

    eval_path = Path(args.eval)
    if not eval_path.exists():
        legacy = PROJECT_ROOT / "eval" / "qa_eval_set.jsonl"
        if legacy.exists():
            eval_path = legacy
        else:
            raise SystemExit(f"Eval file not found: {eval_path}")

    rows = _load_eval(eval_path)
    if not rows:
        raise SystemExit("Eval file is empty or invalid.")

    total = 0
    hits = 0
    rr_sum = 0.0
    hit_at_1 = 0
    target_total = 0
    target_hits = 0
    misses = []

    for row in rows:
        question = (row.get("question") or "").strip()
        if not question:
            continue

        results = retrieve(query=question, legal_area="", k=args.k, chroma_dir=Path(args.chroma_dir))

        if row.get("gold_chunk_id"):
            target_id = row.get("gold_chunk_id")
            rank = _rank_for_target(results, None, None, target_id, args.relax_window, args.relax_document)

            total += 1
            if rank is not None:
                hits += 1
                rr_sum += 1.0 / rank
                if rank == 1:
                    hit_at_1 += 1
                if rank == 1:
                    hit_at_1 += 1
            else:
                misses.append({
                    "id": row.get("id"),
                    "question": question,
                    "gold_chunk_id": target_id,
                })

            required = row.get("required_targets") or {}
            answer = row.get("gold_answer") or ""
            if required and answer:
                target_total += 1
                if _required_targets_satisfied(answer, required):
                    target_hits += 1
        elif bool(row.get("is_multi_hop")):
            paths = row.get("source_paths") or []
            indices = row.get("chunk_indices") or []
            ids = row.get("source_ids") or []
            targets = []
            for p, c, doc_id in zip(paths, indices, ids):
                targets.append((p, _normalize_chunk_index(c), doc_id))

            ranks = []
            for p, c, doc_id in targets:
                ranks.append(_rank_for_target(results, p, c, doc_id, args.relax_window, args.relax_document))

            total += 1
            if ranks and all(r is not None for r in ranks):
                hits += 1
                rr_sum += 1.0 / max(ranks)
            else:
                misses.append({
                    "id": row.get("id"),
                    "question": question,
                    "source_paths": paths,
                    "chunk_indices": indices,
                })
        else:
            target_path = row.get("source_path")
            target_chunk_index = _normalize_chunk_index(row.get("chunk_index"))
            target_id = row.get("source_id")
            rank = _rank_for_target(results, target_path, target_chunk_index, target_id, args.relax_window, args.relax_document)

            total += 1
            if rank is not None:
                hits += 1
                rr_sum += 1.0 / rank
            else:
                misses.append({
                    "id": row.get("id"),
                    "question": question,
                    "source_path": target_path,
                    "chunk_index": target_chunk_index,
                })

    recall = hits / total if total else 0.0
    mrr = rr_sum / total if total else 0.0

    report = {
        "total": total,
        "hits": hits,
        "recall_at_k": recall,
        "mrr": mrr,
        "hit_at_1": hit_at_1 / total if total else 0.0,
        "required_target_hit_rate": target_hits / target_total if target_total else None,
        "k": args.k,
        "misses": misses[:50],
    }

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
