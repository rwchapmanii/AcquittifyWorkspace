from __future__ import annotations

import re
from typing import Final


ORIGINATING_CIRCUIT_LABELS: Final[dict[str, str]] = {
    "ca1": "First Circuit",
    "ca2": "Second Circuit",
    "ca3": "Third Circuit",
    "ca4": "Fourth Circuit",
    "ca5": "Fifth Circuit",
    "ca6": "Sixth Circuit",
    "ca7": "Seventh Circuit",
    "ca8": "Eighth Circuit",
    "ca9": "Ninth Circuit",
    "ca10": "Tenth Circuit",
    "ca11": "Eleventh Circuit",
    "cadc": "D.C. Circuit",
}


_CERTIORARI_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(
        r"(?:on\s+writ\s+of\s+certiorari\s+)?(?:to|from)\s+the\s+united\s+states\s+court\s+of\s+appeals\s+for\s+the\s+(.+?)\s+circuit",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:on\s+writ\s+of\s+certiorari\s+)?(?:to|from)\s+the\s+court\s+of\s+appeals\s+for\s+the\s+(.+?)\s+circuit",
        re.IGNORECASE,
    ),
)

_DIGIT_CIRCUIT_RE: Final[re.Pattern[str]] = re.compile(r"\b(1[01]|[1-9])(st|nd|rd|th)?\b")


def _compact_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_originating_circuit(value: str | None) -> str | None:
    raw = _compact_text(str(value or "")).lower()
    if not raw:
        return None

    no_punct = re.sub(r"[^a-z0-9 ]+", " ", raw)
    normalized = re.sub(r"\s+", " ", no_punct).strip()
    if not normalized:
        return None
    collapsed = normalized.replace(" ", "")

    if normalized in ORIGINATING_CIRCUIT_LABELS:
        return normalized
    if normalized == "dc" or normalized == "d c":
        return "cadc"
    if normalized.startswith("ca") and normalized[2:].isdigit():
        n = int(normalized[2:])
        if 1 <= n <= 11:
            return f"ca{n}"

    if "district of columbia" in normalized or normalized in {"d c", "dc"} or "districtofcolumbia" in collapsed:
        return "cadc"

    token_map = {
        "first": "ca1",
        "second": "ca2",
        "third": "ca3",
        "fourth": "ca4",
        "fifth": "ca5",
        "sixth": "ca6",
        "seventh": "ca7",
        "eighth": "ca8",
        "ninth": "ca9",
        "tenth": "ca10",
        "eleventh": "ca11",
    }
    for token, code in token_map.items():
        if re.search(rf"\b{token}\b", normalized) or token in collapsed:
            return code

    digit_match = _DIGIT_CIRCUIT_RE.search(normalized)
    if digit_match:
        n = int(digit_match.group(1))
        if 1 <= n <= 11:
            return f"ca{n}"

    return None


def extract_originating_circuit(opinion_text: str) -> tuple[str | None, str | None]:
    compact = _compact_text(opinion_text)
    if not compact:
        return None, None

    scan_text = compact[:25000]
    for pattern in _CERTIORARI_PATTERNS:
        match = pattern.search(scan_text)
        if not match:
            continue
        raw_fragment = _compact_text(match.group(1))
        code = normalize_originating_circuit(raw_fragment)
        if code:
            return code, ORIGINATING_CIRCUIT_LABELS.get(code)
        return None, raw_fragment

    return None, None
