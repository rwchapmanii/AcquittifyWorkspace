from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, List, Optional

_CASE_CITE_PATTERN = re.compile(
    r"\b\d{1,3}\s+(?:U\.?\s*S\.?|S\. Ct\.|F\. ?\d+d|F\. ?Supp\. ?\d*d?|L\. ?Ed\. ?\d*d?)\s+\d+\b",
    re.IGNORECASE,
)
_STATE_CITE_PATTERN = re.compile(
    r"\b\d{1,3}\s+(?:N\.E\. ?\d+d|P\. ?\d+d|So\. ?\d+d|S\.E\. ?\d+d|N\.W\. ?\d+d)\s+\d+\b",
    re.IGNORECASE,
)
_USC_PATTERN = re.compile(
    r"\b\d+\s*U\.S\.C\.?\s*§?\s*\d+[a-zA-Z0-9\-]*(?:\([a-zA-Z0-9]+\))*",
    re.IGNORECASE,
)
_CFR_PATTERN = re.compile(
    r"\b\d+\s*C\.F\.R\.?\s*§?\s*\d+(?:\.\d+)*(?:\([a-zA-Z0-9]+\))*",
    re.IGNORECASE,
)
_USC_CAPTURE = re.compile(
    r"\b(\d+)\s*U\.S\.C\.?\s*§?\s*([0-9A-Za-z\-\.\(\)]+)",
    re.IGNORECASE,
)
_CFR_CAPTURE = re.compile(
    r"\b(\d+)\s*C\.F\.R\.?\s*§?\s*([0-9A-Za-z\-\.\(\)]+)",
    re.IGNORECASE,
)
_RULE_PATTERN = re.compile(
    r"\b(Fed\.?\s+R\.?\s+(?:Crim|Civ|Evid|App)\.?\s+P\.?\s*\d+[a-zA-Z0-9]*(?:\([a-zA-Z0-9]+\))*)\b",
    re.IGNORECASE,
)
_SHORT_RULE_PATTERN = re.compile(
    r"\b(?:Rule|FRE|FRCP|FRCrP)\s*\d+[a-zA-Z0-9]*(?:\([a-zA-Z0-9]+\))*",
    re.IGNORECASE,
)

_REPORTER_NORMALIZATIONS = [
    (re.compile(r"\bU\\.\\s*S\\.\b", re.IGNORECASE), "U.S."),
    (re.compile(r"\bS\\.\\s*Ct\\.\b", re.IGNORECASE), "S. Ct."),
    (re.compile(r"\bL\\.\\s*Ed\\.?\\s*2d\b", re.IGNORECASE), "L. Ed. 2d"),
    (re.compile(r"\bL\\.\\s*Ed\\.\b", re.IGNORECASE), "L. Ed."),
    (re.compile(r"\bF\\.\\s*Supp\\.?\\s*3d\b", re.IGNORECASE), "F. Supp. 3d"),
    (re.compile(r"\bF\\.\\s*Supp\\.?\\s*2d\b", re.IGNORECASE), "F. Supp. 2d"),
    (re.compile(r"\bF\\.\\s*Supp\\.\b", re.IGNORECASE), "F. Supp."),
    (re.compile(r"\bF\\.\\s*4th\b", re.IGNORECASE), "F.4th"),
    (re.compile(r"\bF\\.\\s*3d\b", re.IGNORECASE), "F.3d"),
    (re.compile(r"\bF\\.\\s*2d\b", re.IGNORECASE), "F.2d"),
    (re.compile(r"\bF\\.\\s*d\b", re.IGNORECASE), "F."),
    (re.compile(r"\bN\\.\\s*E\\.?\\s*2d\b", re.IGNORECASE), "N.E.2d"),
    (re.compile(r"\bP\\.\\s*2d\b", re.IGNORECASE), "P.2d"),
    (re.compile(r"\bSo\\.\\s*2d\b", re.IGNORECASE), "So.2d"),
    (re.compile(r"\bS\\.\\s*E\\.?\\s*2d\b", re.IGNORECASE), "S.E.2d"),
    (re.compile(r"\bN\\.\\s*W\\.?\\s*2d\b", re.IGNORECASE), "N.W.2d"),
]


def _unique_sorted(values: List[str]) -> List[str]:
    dedup = {v.strip() for v in values if v and v.strip()}
    return sorted(dedup)


def normalize_citation(citation: str) -> str:
    text = re.sub(r"\s+", " ", citation or "").strip()
    if not text:
        return text
    text = re.sub(r"\bU\.?\s*S\.?\b", "U.S.", text, flags=re.IGNORECASE)
    text = re.sub(r"\bS\.?\s*Ct\.?\b", "S. Ct.", text, flags=re.IGNORECASE)
    text = re.sub(r"\bF\.?\s*Supp\.?\s*2d\b", "F. Supp. 2d", text, flags=re.IGNORECASE)
    text = re.sub(r"\bF\.?\s*Supp\.?\s*3d\b", "F. Supp. 3d", text, flags=re.IGNORECASE)
    text = re.sub(r"\bF\.?\s*3d\b", "F.3d", text, flags=re.IGNORECASE)
    text = re.sub(r"\bF\.?\s*2d\b", "F.2d", text, flags=re.IGNORECASE)
    for pattern, replacement in _REPORTER_NORMALIZATIONS:
        text = pattern.sub(replacement, text)
    text = re.sub(r"\bU\.S\.\.+", "U.S.", text)
    text = re.sub(r"\bS\.\s*Ct\.\.+", "S. Ct.", text)
    match = re.match(r"^(\d{1,3})\s+(.+?)\s+(\d+)$", text)
    if match:
        text = f"{match.group(1)} {match.group(2)} {match.group(3)}"
    return text


def normalize_citations(citations: List[str]) -> List[str]:
    return _unique_sorted([normalize_citation(c) for c in citations])


def extract_citations(text: str) -> List[str]:
    matches = []
    matches.extend(_CASE_CITE_PATTERN.findall(text or ""))
    matches.extend(_STATE_CITE_PATTERN.findall(text or ""))
    return _unique_sorted(matches)


def extract_statutes(text: str) -> List[str]:
    matches = []
    matches.extend(_USC_PATTERN.findall(text or ""))
    matches.extend(_CFR_PATTERN.findall(text or ""))
    return _unique_sorted(matches)


def extract_rules(text: str) -> List[str]:
    matches = []
    matches.extend(_RULE_PATTERN.findall(text or ""))
    matches.extend(_SHORT_RULE_PATTERN.findall(text or ""))
    return _unique_sorted(matches)


def extract_citation_data(text: str) -> Dict[str, List[str]]:
    citations = extract_citations(text)
    bluebook_citations = normalize_citations(citations)
    statutes = extract_statutes(text)
    bluebook_statutes = normalize_statutes(statutes)
    rules = extract_rules(text)
    return {
        "citations": citations,
        "bluebook_citations": bluebook_citations,
        "statutes": statutes,
        "bluebook_statutes": bluebook_statutes,
        "rules": rules,
        "citation_count": len(citations),
        "bluebook_citation_count": len(bluebook_citations),
        "statute_count": len(statutes),
        "bluebook_statute_count": len(bluebook_statutes),
        "rule_count": len(rules),
    }


def normalize_statute(statute: str) -> str:
    text = re.sub(r"\s+", " ", statute or "").strip()
    if not text:
        return text
    match = _USC_CAPTURE.search(text)
    if match:
        title = match.group(1)
        section = match.group(2)
        return f"{title} U.S.C. § {section}"
    match = _CFR_CAPTURE.search(text)
    if match:
        title = match.group(1)
        section = match.group(2)
        return f"{title} C.F.R. § {section}"
    return text


def normalize_statutes(statutes: List[str]) -> List[str]:
    return _unique_sorted([normalize_statute(s) for s in statutes])


def infer_year(date_value: Optional[str]) -> Optional[int]:
    if not date_value:
        return None
    try:
        return int(str(date_value)[:4])
    except Exception:
        pass
    try:
        return datetime.fromisoformat(str(date_value)).year
    except Exception:
        return None
