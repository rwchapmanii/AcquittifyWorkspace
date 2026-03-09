from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from acquittify_retriever import retrieve


ISSUE_AREA_MAP = {
    "hearsay": "Evidence",
    "foundation": "Evidence",
    "leading": "Evidence",
    "speculation": "Evidence",
    "prior_bad_acts": "Evidence",
}


def build_query(issue_type: str, snippet: str, jurisdiction: str) -> str:
    base = issue_type.replace("_", " ")
    juris = jurisdiction or "jurisdiction"
    return f"{base} objection {juris} {snippet[:180]}"


def retrieve_authorities(
    issue_type: str,
    snippet: str,
    jurisdiction: str,
    chroma_dir: Optional[Path] = None,
    k: int = 3,
) -> List[Dict[str, object]]:
    legal_area = ISSUE_AREA_MAP.get(issue_type, "Evidence")
    query = build_query(issue_type, snippet, jurisdiction)
    results = retrieve(query=query, legal_area=legal_area, k=k, chroma_dir=chroma_dir)
    authorities: List[Dict[str, object]] = []
    for row in results:
        authorities.append(
            {
                "title": row.get("title"),
                "citation": row.get("bluebook_case_citations") or row.get("citations"),
                "court": row.get("court"),
                "year": row.get("year"),
                "snippet": (row.get("text") or "")[:320],
                "path": row.get("path"),
                "score": row.get("score"),
            }
        )
    return authorities
