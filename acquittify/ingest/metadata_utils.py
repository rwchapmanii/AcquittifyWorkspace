from __future__ import annotations

from typing import Dict, List

import json

from ..authority import compute_authority_weight
from ..metadata_extract import extract_citation_data, infer_year, normalize_citation

_FACET_PRIORITY = ("ISS", "AUTH", "STG", "OFF", "CTX", "GOV", "PRAC")


def _flatten_taxonomy(taxonomy: dict) -> List[str]:
    flat: List[str] = []
    if not isinstance(taxonomy, dict):
        return flat
    for _, codes in taxonomy.items():
        if isinstance(codes, list):
            for code in codes:
                if isinstance(code, str) and code:
                    flat.append(code)
    return sorted(set(flat))


def _select_primary_legal_area(taxonomy: dict) -> str | None:
    if not isinstance(taxonomy, dict):
        return None
    for facet in _FACET_PRIORITY:
        codes = taxonomy.get(facet)
        if isinstance(codes, list):
            for code in sorted(codes):
                if isinstance(code, str) and code:
                    return code
    return None


def _authority_tier(court: str | None, source_type: str | None) -> str:
    c = (court or "").lower()
    s = (source_type or "").lower()
    if "supreme" in c or "scotus" in c or "supreme court" in s:
        return "SCOTUS"
    if "court of appeals" in c or "circuit" in c or s.startswith("court of appeals"):
        return "Circuit"
    if "district" in c or "district" in s:
        return "District"
    if "statute" in s or "u.s.c" in s:
        return "Statute"
    if "rule" in s:
        return "Rule"
    if "regulation" in s or "c.f.r" in s:
        return "Regulation"
    if "treatise" in s or "manual" in s or "benchbook" in s:
        return "Secondary"
    return "Other"


def _binding_circuit(court: str | None) -> str | None:
    if not court:
        return None
    c = str(court).lower()
    if c.startswith("ca") and c[2:].isdigit():
        return f"{int(c[2:])}th Cir."
    if "d.c." in c or "cadc" in c:
        return "D.C. Cir."
    return None


def _ordinal(num: int) -> str:
    if 10 <= num % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(num % 10, "th")
    return f"{num}{suffix}"


def _normalize_court(court: str) -> str:
    if not court:
        return ""
    c = str(court).strip().lower()
    if c in {"scotus", "supreme court", "u.s. supreme court", "us supreme court"}:
        return "U.S."
    if c == "cadc":
        return "D.C. Cir."
    if c.startswith("ca") and c[2:].isdigit():
        num = int(c[2:])
        return f"{_ordinal(num)} Cir."
    if "circuit" in c and any(ch.isdigit() for ch in c):
        digits = "".join(ch for ch in c if ch.isdigit())
        if digits:
            return f"{_ordinal(int(digits))} Cir."
    if "d.c." in c:
        return "D.C. Cir."
    return str(court).strip()


def _format_case_citation(citation: str, case_name: str | None, court: str | None, year: int | None) -> str | None:
    if not citation or not case_name:
        return None
    reporter = normalize_citation(citation)
    parenthetical = None
    if year:
        court_norm = _normalize_court(court or "")
        if court_norm in {"U.S.", ""}:
            parenthetical = f"({year})"
        else:
            parenthetical = f"({court_norm} {year})"
    if parenthetical:
        return f"{case_name}, {reporter} {parenthetical}"
    if year:
        return f"{case_name}, {reporter} ({year})"
    return f"{case_name}, {reporter}"


def augment_chunk_metadata(meta: Dict, text: str) -> Dict:
    updated = dict(meta)
    citation_data = extract_citation_data(text or "")
    updated.update(citation_data)

    if updated.get("year") is None:
        year = infer_year(updated.get("date") or updated.get("date_filed"))
        if year is not None:
            updated["year"] = year

    case_name = updated.get("case_name") or updated.get("case") or updated.get("title")
    court = updated.get("court") or updated.get("court_level")
    year_val = updated.get("year")
    case_citations = []
    for cite in citation_data.get("citations", []) or []:
        formatted = _format_case_citation(cite, case_name, court, year_val if isinstance(year_val, int) else None)
        if formatted:
            case_citations.append(formatted)
    if case_citations:
        updated["bluebook_case_citations"] = case_citations
        updated["bluebook_case_citation_count"] = len(case_citations)
        updated["case_citation_method"] = "case_name_plus_reporter"
        updated["case_citation_is_synthetic"] = True

    if "document_citation" not in updated and updated.get("citation"):
        updated["document_citation"] = updated.get("citation")

    taxonomy_raw = updated.get("taxonomy")
    taxonomy = None
    if isinstance(taxonomy_raw, dict):
        taxonomy = taxonomy_raw
    elif isinstance(taxonomy_raw, str) and taxonomy_raw.strip():
        try:
            taxonomy = json.loads(taxonomy_raw)
        except Exception:
            taxonomy = None
    if taxonomy:
        updated.setdefault("legal_areas_flat", "|".join(_flatten_taxonomy(taxonomy)))
        if updated.get("legal_area") is None:
            updated["legal_area"] = _select_primary_legal_area(taxonomy)

    updated["authority_weight"] = compute_authority_weight(updated, text or "")
    updated.setdefault("authority_tier", _authority_tier(court, updated.get("source_type")))
    updated.setdefault("binding_circuit", _binding_circuit(court))
    return updated
