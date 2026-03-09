#!/usr/bin/env python3
"""Build a canonical CAP case index with cached summaries."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Iterator, Optional, Tuple

import chromadb
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from acquittify.config import CHROMA_COLLECTION

DEFAULT_OUTPUT = Path("reports") / "cap_case_index.jsonl"
DEFAULT_PDF_INDEX = Path("reports") / "cap_pdf_index.jsonl"


def _load_existing_index(path: Path) -> Dict[str, dict]:
    if not path.exists():
        return {}
    existing: Dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        doc_id = payload.get("doc_id")
        if isinstance(doc_id, str):
            existing[doc_id] = payload
    return existing


def _load_pdf_index(path: Path) -> Dict[str, dict]:
    if not path.exists():
        return {}
    mapping: Dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        doc_id = payload.get("doc_id")
        if isinstance(doc_id, str):
            mapping[doc_id] = payload
    return mapping


def _iter_chroma_records(
    chroma_dir: Path, collection_name: str, limit: Optional[int] = None
) -> Iterator[Tuple[dict, str]]:
    client = chromadb.PersistentClient(path=str(chroma_dir))
    collection = client.get_collection(name=collection_name)
    total = collection.count()
    if limit is not None:
        total = min(total, limit)
    offset = 0
    batch = 4000
    while offset < total:
        fetch = min(batch, total - offset)
        res = collection.get(limit=fetch, offset=offset, include=["metadatas", "documents"])
        metas = res.get("metadatas") or []
        docs = res.get("documents") or []
        for meta, doc in zip(metas, docs):
            if isinstance(meta, dict):
                yield meta, (doc or "")
        offset += fetch


def _iter_metadata_jsonl(path: Path) -> Iterator[Tuple[dict, str]]:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            meta = payload.get("metadata") if isinstance(payload, dict) else None
            if not isinstance(meta, dict):
                meta = payload if isinstance(payload, dict) else None
            if not isinstance(meta, dict):
                continue
            text = payload.get("chunk_text") or ""
            yield meta, text


def _normalize_citations(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(v) for v in parsed if v]
        except Exception:
            pass
        return [value]
    return [str(value)]


def _extract_taxonomy_codes(meta: dict) -> list[str]:
    if not isinstance(meta, dict):
        return []
    taxonomy = meta.get("taxonomy")
    codes: list[str] = []
    if isinstance(taxonomy, dict):
        for _, vals in taxonomy.items():
            if isinstance(vals, list):
                codes.extend([v for v in vals if isinstance(v, str)])
    elif isinstance(taxonomy, str) and taxonomy.strip():
        try:
            parsed = json.loads(taxonomy)
            if isinstance(parsed, dict):
                for _, vals in parsed.items():
                    if isinstance(vals, list):
                        codes.extend([v for v in vals if isinstance(v, str)])
        except Exception:
            pass
    return codes


def _extract_year(value: str | None, fallback: str | None = None) -> int | None:
    for candidate in (value, fallback):
        if not candidate:
            continue
        match = re.match(r"(\d{4})", str(candidate))
        if match:
            return int(match.group(1))
    return None


def _sentences(text: str, limit: int = 3) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    parts = [p.strip() for p in parts if p.strip()]
    return " ".join(parts[:limit])


def _heuristic_summary(text: str, meta: dict) -> str:
    case_name = meta.get("case_name") or meta.get("title") or "Unknown case"
    court = meta.get("court") or "Unknown court"
    decision_date = meta.get("decision_date") or meta.get("date") or "Unknown date"
    citation = meta.get("document_citation") or "Unknown citation"
    if not text:
        return (
            f"Issue: {case_name}\n"
            f"Holding: Unknown\n"
            f"Key Facts: Court: {court}; Date: {decision_date}; Citation: {citation}"
        )
    facts = _sentences(text, limit=3)
    issue = facts.split(".")[0].strip() if facts else case_name
    return f"Issue: {issue}\nHolding: Unknown\nKey Facts: {facts}"


def _llm_summary(text: str, meta: dict, model: str, url: str, max_chars: int) -> str | None:
    prompt = f"""
Summarize this case for a case-law library.
Return JSON with keys: issue, holding, key_facts, disposition.
Be concise and factual. If unknown, return \"Unknown\" for that field.

Case name: {meta.get("case_name") or meta.get("title") or "Unknown"}
Court: {meta.get("court") or "Unknown"}
Decision date: {meta.get("decision_date") or meta.get("date") or "Unknown"}
Citation: {meta.get("document_citation") or "Unknown"}

Text excerpt:
{(text or "")[:max_chars]}
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
        response = requests.post(url, json=payload, timeout=60)
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


def build_case_index(
    *,
    chroma_dir: Path,
    collection: str,
    pdf_index_path: Path,
    output_path: Path,
    metadata_jsonl: Optional[Path],
    limit: Optional[int],
    summary_mode: str,
    summary_model: str,
    summary_url: str,
    summary_max_chars: int,
    existing_index: Optional[Path],
    reuse_summaries: bool,
) -> dict:
    pdf_index = _load_pdf_index(pdf_index_path)
    existing = _load_existing_index(existing_index) if existing_index else {}

    cases: Dict[str, dict] = {}

    if metadata_jsonl:
        source_iter = _iter_metadata_jsonl(metadata_jsonl)
    else:
        source_iter = _iter_chroma_records(chroma_dir, collection, limit=limit)

    for meta, text in source_iter:
        doc_id = meta.get("doc_id")
        source = meta.get("source")
        if not isinstance(doc_id, str) or not doc_id.startswith("cap_"):
            if source != "cap-static-case-law":
                continue

        entry = cases.get(doc_id)
        if entry is None:
            entry = {
                "doc_id": doc_id,
                "cap_id": meta.get("cap_id"),
                "case_name": meta.get("case_name") or meta.get("title"),
                "court": meta.get("court"),
                "decision_date": meta.get("decision_date") or meta.get("date"),
                "year": _extract_year(meta.get("decision_date"), meta.get("date")),
                "citations": _normalize_citations(meta.get("citations")),
                "document_citation": meta.get("document_citation"),
                "reporter_slug": meta.get("reporter_slug"),
                "authority_weight": meta.get("authority_weight"),
                "authority_tier": meta.get("authority_tier"),
                "citation_count": meta.get("citation_count"),
                "source_type": meta.get("source_type"),
                "taxonomy_codes": [],
                "summary": None,
                "summary_method": None,
                "summary_updated_at": None,
                "sample_text": "",
            }
            cases[doc_id] = entry

        if not entry.get("case_name") and (meta.get("case_name") or meta.get("title")):
            entry["case_name"] = meta.get("case_name") or meta.get("title")
        if not entry.get("court") and meta.get("court"):
            entry["court"] = meta.get("court")
        if not entry.get("decision_date") and (meta.get("decision_date") or meta.get("date")):
            entry["decision_date"] = meta.get("decision_date") or meta.get("date")
        if entry.get("year") is None:
            entry["year"] = _extract_year(meta.get("decision_date"), meta.get("date"))
        if not entry.get("document_citation") and meta.get("document_citation"):
            entry["document_citation"] = meta.get("document_citation")
        if not entry.get("reporter_slug") and meta.get("reporter_slug"):
            entry["reporter_slug"] = meta.get("reporter_slug")

        citations = _normalize_citations(meta.get("citations"))
        if citations:
            entry["citations"] = citations

        weight = meta.get("authority_weight")
        if weight is not None:
            try:
                weight_val = float(weight)
                current = entry.get("authority_weight")
                if current is None or weight_val > float(current):
                    entry["authority_weight"] = weight_val
            except Exception:
                pass
        if not entry.get("authority_tier") and meta.get("authority_tier"):
            entry["authority_tier"] = meta.get("authority_tier")

        citation_count = meta.get("citation_count")
        if citation_count is not None:
            try:
                count_val = int(citation_count)
                current = entry.get("citation_count")
                if current is None or count_val > int(current):
                    entry["citation_count"] = count_val
            except Exception:
                pass

        if text and len(text) > len(entry.get("sample_text") or ""):
            entry["sample_text"] = text

        taxonomy_codes = _extract_taxonomy_codes(meta)
        if taxonomy_codes:
            existing_codes = set(entry.get("taxonomy_codes") or [])
            existing_codes.update(taxonomy_codes)
            entry["taxonomy_codes"] = sorted(existing_codes)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.utcnow().isoformat() + "Z"
    with output_path.open("w", encoding="utf-8") as handle:
        for doc_id, entry in cases.items():
            pdf_entry = pdf_index.get(doc_id) or {}
            entry["pdf_path"] = pdf_entry.get("pdf_path")

            if reuse_summaries and existing.get(doc_id, {}).get("summary"):
                entry["summary"] = existing[doc_id]["summary"]
                entry["summary_method"] = existing[doc_id].get("summary_method") or "reused"
                entry["summary_updated_at"] = existing[doc_id].get("summary_updated_at") or now
            else:
                summary_text = None
                summary_method = "none"
                if summary_mode == "llm":
                    summary_method = "llm"
                    summary_text = _llm_summary(
                        entry.get("sample_text") or "",
                        entry,
                        summary_model,
                        summary_url,
                        summary_max_chars,
                    )
                if summary_text is None and summary_mode == "heuristic":
                    summary_text = _heuristic_summary(entry.get("sample_text") or "", entry)
                    summary_method = "heuristic"
                elif summary_text is None and summary_mode == "llm":
                    summary_text = _heuristic_summary(entry.get("sample_text") or "", entry)
                    summary_method = "heuristic_fallback"
                entry["summary"] = summary_text
                entry["summary_method"] = summary_method
                entry["summary_updated_at"] = now if summary_text else None

            entry.pop("sample_text", None)
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return {
        "cases": len(cases),
        "output": str(output_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a canonical CAP case index.")
    parser.add_argument("--chroma-dir", default="Corpus/Chroma", help="Chroma directory")
    parser.add_argument("--collection", default=CHROMA_COLLECTION, help="Chroma collection name")
    parser.add_argument("--pdf-index", default=str(DEFAULT_PDF_INDEX), help="CAP PDF index JSONL")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output JSONL path")
    parser.add_argument("--metadata-jsonl", default=None, help="Optional metadata JSONL for small runs")
    parser.add_argument("--limit", type=int, default=None, help="Limit total chunks scanned")
    parser.add_argument(
        "--summary-mode",
        default=os.getenv("ACQUITTIFY_LIBRARY_SUMMARY_MODE", "heuristic"),
        choices=["heuristic", "llm", "none"],
        help="Summary mode",
    )
    parser.add_argument(
        "--summary-model",
        default=os.getenv("ACQUITTIFY_LIBRARY_SUMMARY_MODEL", "acquittify-qwen"),
        help="LLM model for summaries",
    )
    parser.add_argument(
        "--summary-url",
        default=os.getenv("ACQUITTIFY_LIBRARY_SUMMARY_URL", "http://localhost:11434/api/chat"),
        help="LLM URL for summaries",
    )
    parser.add_argument("--summary-max-chars", type=int, default=4000, help="Max chars for LLM summary")
    parser.add_argument("--existing-index", default=None, help="Existing index to reuse summaries")
    parser.add_argument("--reuse-summaries", action="store_true", help="Reuse summaries from existing index")
    args = parser.parse_args()

    summary = build_case_index(
        chroma_dir=Path(args.chroma_dir),
        collection=args.collection,
        pdf_index_path=Path(args.pdf_index),
        output_path=Path(args.output),
        metadata_jsonl=Path(args.metadata_jsonl) if args.metadata_jsonl else None,
        limit=args.limit,
        summary_mode=args.summary_mode,
        summary_model=args.summary_model,
        summary_url=args.summary_url,
        summary_max_chars=args.summary_max_chars,
        existing_index=Path(args.existing_index) if args.existing_index else None,
        reuse_summaries=args.reuse_summaries,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
