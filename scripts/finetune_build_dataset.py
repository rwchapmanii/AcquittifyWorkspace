#!/usr/bin/env python3
"""Build SFT dataset from repo QA content with Acquittify memo requirements.

Default source: eval/qa_eval_set.jsonl (contains question/answer + source excerpts).
Output: finetune/data/train.jsonl + finetune/data/val.jsonl
"""

from __future__ import annotations

import argparse
import json
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = PROJECT_ROOT / "eval" / "qa_eval_set.jsonl"
DEFAULT_OUT_DIR = PROJECT_ROOT / "finetune" / "data"
APP_PATH = PROJECT_ROOT / "app.py"

SYSTEM_PROMPT_MARKER = 'SYSTEM_PROMPT = """'


@dataclass
class SourceDoc:
    title: str
    source_type: str
    path: str
    chunk_index: str
    text: str


def load_system_prompt(app_path: Path) -> str:
    text = app_path.read_text(encoding="utf-8")
    if SYSTEM_PROMPT_MARKER not in text:
        raise ValueError("SYSTEM_PROMPT marker not found in app.py")
    tail = text.split(SYSTEM_PROMPT_MARKER, 1)[1]
    return tail.split('"""', 1)[0].strip()


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def infer_tier(text: str) -> str:
    lowered = (text or "").lower()
    if "u.s.c." in lowered or "usc" in lowered or "§" in lowered:
        return "Statute"
    if "c.f.r." in lowered:
        return "Reg"
    if "fed. r." in lowered or re.search(r"\brule\s+\d+", lowered):
        return "Rule"
    if re.search(r"\bv\.\s", text or ""):
        return "Case"
    return "Case"


def build_sources_message(sources: List[SourceDoc]) -> Dict[str, str]:
    if not sources:
        return {
            "role": "system",
            "content": (
                "SOURCES:\n"
                "(No relevant authority was retrieved from the Acquittify corpus for this query.)\n\n"
                "You may NOT cite any case, statute, or authority.\n"
                "Use [TBV] where verification is required and specify what documents must be added."
            ),
        }

    lines = [
        "SOURCES (authoritative excerpts from Acquittify corpus):",
        "You may rely ONLY on the excerpts below and must cite them as [SRC: DOC####].",
        "Use any CITATIONS/STATUTES/RULES lines in the excerpts as authority hints, but still cite with [SRC: DOC####].",
        "",
    ]
    for idx, src in enumerate(sources, start=1):
        lines.append(f"[SRC: DOC{idx:04d}]")
        lines.append(f"TITLE: {src.title}")
        lines.append(f"SOURCE_TYPE: {src.source_type}")
        lines.append(f"PATH: {src.path}")
        lines.append(f"CHUNK_INDEX: {src.chunk_index}")
        lines.append("----")
        lines.append(src.text)
        lines.append("")
    return {"role": "system", "content": "\n".join(lines).strip()}


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def extract_sources(item: Dict[str, Any], max_chars: int) -> List[SourceDoc]:
    texts = _as_list(item.get("source_texts") or item.get("source_text"))
    ids = _as_list(item.get("source_ids") or item.get("source_id"))
    paths = _as_list(item.get("source_paths") or item.get("source_path"))
    types = _as_list(item.get("source_types") or item.get("source_type"))
    titles = _as_list(item.get("titles") or item.get("title"))
    chunks = _as_list(item.get("chunk_indices") or item.get("chunk_index"))

    sources: List[SourceDoc] = []
    for i, text in enumerate(texts):
        if not text:
            continue
        text = text.strip()
        if max_chars and len(text) > max_chars:
            text = text[:max_chars].rstrip() + "..."
        sources.append(
            SourceDoc(
                title=str(titles[i]) if i < len(titles) and titles[i] is not None else "unknown",
                source_type=str(types[i]) if i < len(types) and types[i] is not None else "unknown",
                path=str(paths[i]) if i < len(paths) and paths[i] is not None else "",
                chunk_index=str(chunks[i]) if i < len(chunks) and chunks[i] is not None else "",
                text=text,
            )
        )
    return sources


def build_irac_answer(question: str, answer: str, sources: List[SourceDoc]) -> str:
    answer = normalize_ws(answer)
    question = normalize_ws(question)
    if not sources:
        return (
            "Issue\n"
            "Based on the available record, the requested legal point cannot be confirmed without sources. "
            "This conclusion is limited by the absence of authority.\n"
            f"**Issue:** {question}\n\n"
            "Rule\n"
            "No relevant sources were provided, so the governing rule cannot be verified. [TBV] "
            "Please provide the controlling authority (case, statute, rule, or regulation).\n\n"
            "Analysis\n"
            "Without sources, any analysis would be speculative and could misstate the law. [TBV]\n\n"
            "Conclusion\n"
            "No supported answer can be given until sources are provided. [TBV]\n"
            "1. What jurisdiction and governing authority apply?\n"
            "2. What primary source (case/statute/rule) should control this issue?\n"
            "3. Are there cited excerpts from the corpus that address this question?"
        )

    src_tags = [f"[SRC: DOC{i+1:04d}]" for i in range(len(sources))]
    cite_all = " ".join(src_tags)

    ladder_lines = ["Authority Ladder:"]
    for i, src in enumerate(sources, start=1):
        tier = infer_tier(src.text)
        ladder_lines.append(f"{i}. {tier} — [SRC: DOC{i:04d}]")
    ladder = "\n".join(ladder_lines)

    issue = (
        "Issue\n"
        f"Based on the provided sources, the answer is: {answer}. {cite_all}\n"
        "This conclusion is limited to what the cited excerpt(s) expressly state.\n"
        f"**Issue:** {question}\n"
    )

    rule = (
        "Rule\n"
        f"{ladder}\n"
        f"The excerpted authority states: {answer}. {cite_all}\n"
    )

    analysis = (
        "Analysis\n"
        f"Applying the cited authority to the question, the text directly provides the requested detail: {answer}. {cite_all}\n"
    )

    conclusion = (
        "Conclusion\n"
        f"Therefore, the supported answer is: {answer}. {cite_all}\n"
        "1. What jurisdiction or forum governs this issue?\n"
        "2. What is the procedural posture and standard of review?\n"
        "3. Are there additional controlling authorities in the corpus that refine this point?"
    )

    return "\n\n".join([issue.strip(), rule.strip(), analysis.strip(), conclusion.strip()])


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
    return items


def split_items(items: List[Dict[str, Any]], val_ratio: float) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if not items:
        return [], []
    val_count = max(1, int(len(items) * val_ratio)) if val_ratio > 0 else 0
    return items[:-val_count], items[-val_count:] if val_count else (items, [])


def write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False))
            f.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Acquittify SFT dataset from repo QA content")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="QA JSONL source file")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="Output directory")
    parser.add_argument("--limit", type=int, default=80, help="Max examples")
    parser.add_argument("--shuffle", action="store_true", help="Shuffle before sampling")
    parser.add_argument("--seed", type=int, default=13, help="Random seed")
    parser.add_argument("--val-ratio", type=float, default=0.1, help="Validation split ratio")
    parser.add_argument("--max-source-chars", type=int, default=2000, help="Truncate source excerpts")
    args = parser.parse_args()

    system_prompt = load_system_prompt(APP_PATH)
    items = load_jsonl(args.source)

    if args.shuffle:
        random.seed(args.seed)
        random.shuffle(items)

    if args.limit:
        items = items[: args.limit]

    examples: List[Dict[str, Any]] = []
    for item in items:
        question = item.get("question") or ""
        answer = item.get("answer") or item.get("gold_answer") or ""
        if not answer and item.get("answer_spans"):
            answer = " ".join([normalize_ws(span) for span in item.get("answer_spans") or []])
        if not question or not answer:
            continue

        sources = extract_sources(item, args.max_source_chars)
        sources_msg = build_sources_message(sources)
        assistant = build_irac_answer(question, answer, sources)

        messages = [
            {"role": "system", "content": system_prompt},
            sources_msg,
            {"role": "user", "content": question},
            {"role": "assistant", "content": assistant},
        ]
        examples.append({"messages": messages, "meta": {"id": item.get("id")}})

    train_items, val_items = split_items(examples, args.val_ratio)

    out_dir = args.out_dir
    train_path = out_dir / "train.jsonl"
    val_path = out_dir / "val.jsonl"
    write_jsonl(train_path, train_items)
    if val_items:
        write_jsonl(val_path, val_items)

    manifest = {
        "source": str(args.source),
        "total_examples": len(examples),
        "train_examples": len(train_items),
        "val_examples": len(val_items),
        "limit": args.limit,
        "val_ratio": args.val_ratio,
        "max_source_chars": args.max_source_chars,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
