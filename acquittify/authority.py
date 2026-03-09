from __future__ import annotations

from typing import Dict, Optional

from .metadata_extract import extract_citation_data


def _court_score(court: Optional[str]) -> int:
    if not court:
        return 0
    c = str(court).lower()
    if "scotus" in c or "supreme" in c:
        return 5
    if c.startswith("ca") or "court of appeals" in c or "circuit" in c:
        return 4
    if "district" in c:
        return 3
    if "state" in c and "supreme" in c:
        return 3
    return 1


def _source_type_score(source_type: Optional[str]) -> int:
    if not source_type:
        return 0
    s = str(source_type).lower()
    if "supreme court" in s or "scotus" in s:
        return 5
    if "court of appeals" in s or "circuit" in s:
        return 4
    if "district" in s:
        return 3
    if "treatise" in s or "manual" in s or "benchbook" in s:
        return 2
    if "statute" in s or "regulation" in s:
        return 3
    if "transcript" in s:
        return 1
    return 1


def compute_authority_weight(meta: Dict, text: str) -> int:
    court_score = _court_score(meta.get("court") or meta.get("court_id"))
    source_score = _source_type_score(meta.get("source_type"))
    citation_data = extract_citation_data(text or "")
    citation_bonus = 1 if citation_data["citation_count"] >= 2 else 0
    statute_bonus = 1 if citation_data["statute_count"] >= 1 else 0
    rule_bonus = 1 if citation_data["rule_count"] >= 1 else 0
    base = max(court_score, source_score)
    return int(base + citation_bonus + statute_bonus + rule_bonus)
