from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

from acquittify.metadata_extract import normalize_citation


DOCKET_CLEAN_RE = re.compile(r"[^0-9A-Z-]")
CASE_NAME_TOKEN_RE = re.compile(r"[a-z0-9]+")
CASE_NAME_SKIP = {"et", "al", "the", "of", "and", "for", "in", "re", "a", "an", "by"}


@dataclass(frozen=True)
class CitationMatch:
    us_cite: str
    case_id: str
    case_name: str
    decision_date: str
    match_method: str


def _normalize_docket(value: str) -> str:
    token = str(value or "").strip().upper()
    token = token.replace("NO.", "").replace("NO", "")
    token = token.replace(" ", "")
    token = DOCKET_CLEAN_RE.sub("", token)
    return token


def _normalize_case_name(value: str) -> str:
    text = str(value or "").lower()
    text = text.replace(" vs. ", " v ").replace(" vs ", " v ")
    text = re.sub(r"[^a-z0-9\\s.]", " ", text)
    text = re.sub(r"\\bv\\.\\b", " v ", text)
    text = re.sub(r"\\bv\\b", " v ", text)
    return re.sub(r"\\s+", " ", text).strip()


def _case_name_signature(value: str) -> tuple[str, str]:
    normalized = _normalize_case_name(value)
    if " v " not in normalized:
        return ("", "")
    left, right = normalized.split(" v ", 1)
    left_tokens = [token for token in CASE_NAME_TOKEN_RE.findall(left) if token not in CASE_NAME_SKIP]
    right_tokens = [token for token in CASE_NAME_TOKEN_RE.findall(right) if token not in CASE_NAME_SKIP]
    if not left_tokens or not right_tokens:
        return ("", "")
    return (left_tokens[0], right_tokens[0])


def _normalize_us_cite(value: str) -> str:
    normalized = normalize_citation(str(value or ""))
    if "_" in normalized:
        return ""
    return normalized


class ScotusCitationDB:
    def __init__(self, payload: dict[str, Any]):
        self.source = str(payload.get("source") or "")
        self.source_url = str(payload.get("source_url") or "")
        self.version = str(payload.get("version") or "")
        self.generated_at = str(payload.get("generated_at") or "")
        self.by_docket = payload.get("by_docket") or {}
        self.by_name_year = payload.get("by_name_year") or {}

    def match(self, docket: str, case_name: str | None = None, decision_date: str | None = None) -> CitationMatch | None:
        docket_key = _normalize_docket(docket or "")
        candidates = list(self.by_docket.get(docket_key) or [])
        if not candidates and case_name:
            return self.match_by_name_year(case_name, decision_date)
        if len(candidates) == 1:
            return _entry_to_match(candidates[0], "docket")

        if case_name:
            signature = _case_name_signature(case_name)
            if signature != ("", ""):
                filtered = [entry for entry in candidates if tuple(entry.get("signature") or ("", "")) == signature]
                if len(filtered) == 1:
                    return _entry_to_match(filtered[0], "docket+case_name")
            normalized = _normalize_case_name(case_name)
            filtered = [
                entry
                for entry in candidates
                if normalized and normalized in str(entry.get("normalized_case_name") or "")
            ]
            if len(filtered) == 1:
                return _entry_to_match(filtered[0], "docket+case_name")

        if decision_date:
            year = str(decision_date)[:4]
            filtered = [entry for entry in candidates if str(entry.get("decision_date") or "")[:4] == year]
            if len(filtered) == 1:
                return _entry_to_match(filtered[0], "docket+date")

        if candidates:
            return _entry_to_match(candidates[0], "docket_ambiguous")
        return None

    def match_by_name_year(self, case_name: str, decision_date: str | None = None) -> CitationMatch | None:
        normalized = _normalize_case_name(case_name or "")
        if not normalized:
            return None
        year = str(decision_date)[:4] if decision_date else ""
        key = f"{normalized}|{year}" if year else normalized
        candidates = list(self.by_name_year.get(key) or [])
        if len(candidates) == 1:
            return _entry_to_match(candidates[0], "case_name_year")
        if candidates:
            return _entry_to_match(candidates[0], "case_name_ambiguous")
        return None


def _entry_to_match(entry: dict[str, Any], method: str) -> CitationMatch:
    return CitationMatch(
        us_cite=str(entry.get("us_cite") or ""),
        case_id=str(entry.get("case_id") or ""),
        case_name=str(entry.get("case_name") or ""),
        decision_date=str(entry.get("decision_date") or ""),
        match_method=method,
    )


def load_scotus_citation_db(path: Path | str | None) -> ScotusCitationDB | None:
    if not path:
        return None
    db_path = Path(path).expanduser().resolve()
    if not db_path.exists():
        return None
    payload = json.loads(db_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    return ScotusCitationDB(payload)

