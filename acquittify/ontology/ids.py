from __future__ import annotations

import hashlib
import re
from datetime import datetime


_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str, max_len: int = 48) -> str:
    lowered = (text or "").lower()
    cleaned = _NON_ALNUM_RE.sub("_", lowered).strip("_")
    return cleaned[:max_len] if cleaned else "unknown"


def normalize_citation_token(citation: str, compact: bool = False) -> str:
    token = _slug(citation, max_len=64)
    token = token.replace("u_s", "us").replace("s_ct", "sct")
    if compact:
        return token.replace("_", "")
    return token


def _extract_case_short_name(title: str) -> str:
    if not title:
        return "unknown"
    normalized = title.replace(" vs. ", " v. ").replace(" vs ", " v ")
    left = re.split(r"\bv\.?\b", normalized, maxsplit=1, flags=re.IGNORECASE)[0]
    return _slug(left, max_len=32)


def _year_from_date(date_decided: str) -> str:
    raw = (date_decided or "").strip()
    if re.fullmatch(r"\d{4}", raw):
        return raw
    try:
        return str(datetime.fromisoformat(raw).year)
    except Exception:
        return "0000"


def stable_hash(value: str, size: int = 12) -> str:
    return hashlib.sha1((value or "").encode("utf-8")).hexdigest()[:size]


def build_case_id(
    jurisdiction: str,
    court: str,
    date_decided: str,
    title: str,
    primary_citation: str,
) -> str:
    jurisdiction_slug = _slug(jurisdiction, max_len=16)
    court_slug = _slug(court, max_len=24)
    year = _year_from_date(date_decided)
    short_name = _extract_case_short_name(title)
    citation_compact = normalize_citation_token(primary_citation, compact=True)
    return f"{jurisdiction_slug}.{court_slug}.{year}.{short_name}.{citation_compact}"


def build_holding_id(case_id: str, index: int) -> str:
    if index < 1:
        raise ValueError("holding index must start at 1")
    parts = case_id.split(".")
    base = ".".join(parts[:-1]) if len(parts) > 1 else case_id
    return f"{base}.H{index}"


def build_issue_id(domain: str, doctrine: str, rule_type: str) -> str:
    return f"issue.{_slug(domain, 32)}.{_slug(doctrine, 48)}.{_slug(rule_type, 48)}"


def case_note_filename(case_id: str, primary_citation: str | None = None) -> str:
    parts = case_id.split(".")
    if len(parts) < 5:
        return f"case__{_slug(case_id, 120)}.md"
    jurisdiction, court, year, short_name = parts[0], parts[1], parts[2], parts[3]
    citation_token = normalize_citation_token(primary_citation or parts[-1], compact=False)
    return f"case__{jurisdiction}__{court}__{year}__{short_name}__{citation_token}.md"


def holding_note_filename(case_id: str, index: int) -> str:
    holding_id = build_holding_id(case_id, index)
    short_name = case_id.split(".")[3] if len(case_id.split(".")) >= 4 else "unknown"
    suffix = holding_id.split(".")[-1]
    return f"holding__{short_name}__{suffix}.md"


def issue_note_filename(issue_id: str) -> str:
    parts = issue_id.split(".")
    if len(parts) < 4:
        return f"issue__{_slug(issue_id, 120)}.md"
    _, domain, doctrine, rule_type = parts[:4]
    return f"issue__{domain}__{doctrine}__{rule_type}.md"
