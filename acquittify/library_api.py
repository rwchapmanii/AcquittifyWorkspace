from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from acquittify_retriever import retrieve
from acquittify.paths import CHROMA_DIR

app = FastAPI(title="Acquittify Caselaw Library")

CASE_INDEX_PATH = Path("reports") / "cap_case_index.jsonl"
PDF_INDEX_PATH = Path("reports") / "cap_pdf_index.jsonl"

_case_index_cache: Dict[str, dict] = {}
_case_index_mtime: float | None = None
_pdf_index_cache: Dict[str, dict] = {}
_pdf_index_mtime: float | None = None


def _load_index(path: Path) -> dict:
    if not path.exists():
        return {}
    index: Dict[str, dict] = {}
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            doc_id = payload.get("doc_id")
            if isinstance(doc_id, str):
                index[doc_id] = payload
    return index


def _get_case_index() -> dict:
    global _case_index_cache, _case_index_mtime
    if not CASE_INDEX_PATH.exists():
        return {}
    mtime = CASE_INDEX_PATH.stat().st_mtime
    if _case_index_mtime != mtime:
        _case_index_cache = _load_index(CASE_INDEX_PATH)
        _case_index_mtime = mtime
    return _case_index_cache


def _get_pdf_index() -> dict:
    global _pdf_index_cache, _pdf_index_mtime
    if not PDF_INDEX_PATH.exists():
        return {}
    mtime = PDF_INDEX_PATH.stat().st_mtime
    if _pdf_index_mtime != mtime:
        _pdf_index_cache = _load_index(PDF_INDEX_PATH)
        _pdf_index_mtime = mtime
    return _pdf_index_cache


def _group_results(results: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for item in results:
        doc_id = item.get("doc_id") or item.get("id")
        if not doc_id:
            continue
        existing = grouped.get(doc_id)
        if not existing or item.get("score", 0) > existing.get("score", 0):
            grouped[doc_id] = item
    return grouped


def _apply_filters(
    items: List[Dict[str, Any]],
    court: Optional[str],
    year_from: Optional[int],
    year_to: Optional[int],
    authority_tier: Optional[str],
    min_authority: Optional[float],
) -> List[Dict[str, Any]]:
    filtered = []
    for item in items:
        court_val = item.get("court") or ""
        if court and court.lower() not in str(court_val).lower():
            continue
        year_val = item.get("year")
        if year_val is not None:
            try:
                year_val = int(year_val)
            except Exception:
                year_val = None
        if year_from and year_val and year_val < year_from:
            continue
        if year_to and year_val and year_val > year_to:
            continue
        if authority_tier and item.get("authority_tier"):
            if authority_tier.lower() not in str(item.get("authority_tier")).lower():
                continue
        if min_authority is not None:
            try:
                auth = float(item.get("authority_weight") or 0)
            except Exception:
                auth = 0.0
            if auth < min_authority:
                continue
        filtered.append(item)
    return filtered


def _sort_results(items: List[Dict[str, Any]], sort: str) -> List[Dict[str, Any]]:
    if sort == "authority":
        return sorted(items, key=lambda d: float(d.get("authority_weight") or 0), reverse=True)
    if sort == "date_desc":
        return sorted(items, key=lambda d: int(d.get("year") or 0), reverse=True)
    if sort == "date_asc":
        return sorted(items, key=lambda d: int(d.get("year") or 0))
    if sort == "citations":
        return sorted(items, key=lambda d: int(d.get("citation_count") or 0), reverse=True)
    return sorted(items, key=lambda d: float(d.get("score") or 0), reverse=True)


def _related_cases(doc_id: str, limit: int = 5) -> list[dict]:
    case_index = _get_case_index()
    current = case_index.get(doc_id)
    if not current:
        return []
    court = str(current.get("court") or "").lower()
    reporter = str(current.get("reporter_slug") or "").lower()
    taxonomy = set(current.get("taxonomy_codes") or [])

    def _normalize_citations(value) -> set[str]:
        if value is None:
            return set()
        if isinstance(value, list):
            return {str(v).lower() for v in value if v}
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return {str(v).lower() for v in parsed if v}
            except Exception:
                pass
            return {value.lower()}
        return {str(value).lower()}

    def _tier_rank(value: str | None) -> int:
        if not value:
            return 0
        lower = value.lower()
        if "supreme" in lower:
            return 4
        if "circuit" in lower or "appellate" in lower:
            return 3
        if "district" in lower or "trial" in lower:
            return 2
        return 1

    base_citations = _normalize_citations(current.get("citations"))
    if current.get("document_citation"):
        base_citations.add(str(current.get("document_citation")).lower())
    base_rank = _tier_rank(current.get("authority_tier"))
    candidates = []
    for other_id, row in case_index.items():
        if other_id == doc_id:
            continue
        score = 0.0
        if court and str(row.get("court") or "").lower() == court:
            score += 3.0
        if reporter and str(row.get("reporter_slug") or "").lower() == reporter:
            score += 1.0
        other_tax = set(row.get("taxonomy_codes") or [])
        if taxonomy and other_tax:
            score += min(len(taxonomy.intersection(other_tax)), 6)
        other_citations = _normalize_citations(row.get("citations"))
        if row.get("document_citation"):
            other_citations.add(str(row.get("document_citation")).lower())
        if base_citations and other_citations:
            score += min(len(base_citations.intersection(other_citations)), 5) * 1.5
        other_rank = _tier_rank(row.get("authority_tier"))
        if base_rank and other_rank:
            score += max(0.0, 2.0 - abs(base_rank - other_rank))
        if score > 0:
            candidates.append((score, row))
    candidates.sort(key=lambda c: c[0], reverse=True)
    return [row for _, row in candidates[:limit]]


def _strip_llm_summary(record: dict) -> dict:
    summary_method = str(record.get("summary_method") or "").lower()
    if summary_method.startswith("llm"):
        cleaned = dict(record)
        cleaned.pop("summary", None)
        return cleaned
    return record


@app.get("/healthz")
def healthcheck() -> dict:
    return {"status": "ok"}


@app.get("/library/search")
def library_search(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=200),
    court: Optional[str] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    authority_tier: Optional[str] = None,
    min_authority: Optional[float] = None,
    sort: str = Query("score", pattern="^(score|authority|date_desc|date_asc|citations)$"),
) -> dict:
    results = retrieve(query=q, legal_area="", k=max(limit * 4, 40), chroma_dir=CHROMA_DIR)
    grouped = _group_results(results)

    case_index = _get_case_index()
    pdf_index = _get_pdf_index()
    items: List[Dict[str, Any]] = []
    for doc_id, item in grouped.items():
        merged = dict(item)
        case_meta = _strip_llm_summary(case_index.get(doc_id, {}))
        merged.update({k: v for k, v in case_meta.items() if v is not None})
        pdf_meta = pdf_index.get(doc_id, {})
        if not merged.get("pdf_path") and pdf_meta.get("pdf_path"):
            merged["pdf_path"] = pdf_meta.get("pdf_path")
        merged["doc_id"] = doc_id
        items.append(merged)

    filtered = _apply_filters(items, court, year_from, year_to, authority_tier, min_authority)
    sorted_items = _sort_results(filtered, sort)
    return {"query": q, "total": len(sorted_items), "results": sorted_items[:limit]}


@app.get("/library/case/{doc_id}")
def library_case(doc_id: str) -> dict:
    case_index = _get_case_index()
    record = case_index.get(doc_id)
    if not record:
        raise HTTPException(status_code=404, detail="Case not found in index")
    return _strip_llm_summary(record)


@app.get("/library/case/{doc_id}/related")
def library_case_related(doc_id: str, limit: int = Query(5, ge=1, le=25)) -> dict:
    return {"doc_id": doc_id, "related": _related_cases(doc_id, limit=limit)}


@app.get("/library/pdf/{doc_id}")
def library_pdf(doc_id: str):
    case_index = _get_case_index()
    pdf_index = _get_pdf_index()
    record = case_index.get(doc_id) or pdf_index.get(doc_id)
    if not record:
        raise HTTPException(status_code=404, detail="PDF mapping not found")
    pdf_path = record.get("pdf_path")
    if not pdf_path:
        raise HTTPException(status_code=404, detail="PDF path missing")
    path = Path(pdf_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="PDF file missing")
    return FileResponse(path, media_type="application/pdf", filename=path.name)
