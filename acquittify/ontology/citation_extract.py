from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from acquittify.metadata_extract import normalize_citation

try:
    from eyecite import get_citations  # type: ignore
except Exception:  # pragma: no cover
    get_citations = None


_CASE_PATTERN = re.compile(
    r"\b\d{1,4}\s+(?:U\.?\s*S\.?|S\. ?Ct\.|F\. ?\d+d|F\. ?Supp\. ?\d*d?|L\. ?Ed\. ?\d*d?)\s+(?:\d+|_{2,})\b",
    re.IGNORECASE,
)
_STATE_PATTERN = re.compile(
    r"\b\d{1,4}\s+(?:N\.E\. ?\d+d|P\. ?\d+d|So\. ?\d+d|S\.E\. ?\d+d|N\.W\. ?\d+d)\s+\d+\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CitationMention:
    raw_text: str
    normalized_text: str
    start_char: int
    end_char: int
    extractor: str
    kind: str = "case"


def _iter_regex_mentions(text: str) -> Iterable[CitationMention]:
    for pattern in (_CASE_PATTERN, _STATE_PATTERN):
        for match in pattern.finditer(text or ""):
            raw = match.group(0)
            yield CitationMention(
                raw_text=raw,
                normalized_text=normalize_citation(raw),
                start_char=match.start(),
                end_char=match.end(),
                extractor="regex",
                kind="case",
            )


def _coerce_span(obj) -> tuple[int, int] | None:
    span = getattr(obj, "span", None)
    if callable(span):
        try:
            span = span()
        except Exception:
            span = None
    if isinstance(span, tuple) and len(span) == 2 and all(isinstance(x, int) for x in span):
        return span
    start = getattr(obj, "span_start", None)
    end = getattr(obj, "span_end", None)
    if isinstance(start, int) and isinstance(end, int):
        return start, end
    start = getattr(obj, "start", None)
    end = getattr(obj, "end", None)
    if isinstance(start, int) and isinstance(end, int):
        return start, end
    return None


def _coerce_raw_text(obj, text: str, span: tuple[int, int] | None) -> str:
    for attr in ("matched_text", "corrected_citation", "citation", "text"):
        value = getattr(obj, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if span:
        return text[span[0] : span[1]].strip()
    return ""


def _iter_eyecite_mentions(text: str) -> Iterable[CitationMention]:
    if get_citations is None:
        return []

    mentions: list[CitationMention] = []
    for cite in get_citations(text or ""):
        span = _coerce_span(cite)
        raw = _coerce_raw_text(cite, text, span)
        if not raw:
            continue

        start_char: int
        end_char: int
        if span:
            start_char, end_char = span
        else:
            start_char = text.find(raw)
            if start_char < 0:
                continue
            end_char = start_char + len(raw)

        mentions.append(
            CitationMention(
                raw_text=raw,
                normalized_text=normalize_citation(raw),
                start_char=start_char,
                end_char=end_char,
                extractor="eyecite",
                kind="case",
            )
        )
    return mentions


def extract_citation_mentions(text: str) -> list[CitationMention]:
    mentions: list[CitationMention] = []

    eye_mentions = list(_iter_eyecite_mentions(text))
    if eye_mentions:
        mentions.extend(eye_mentions)

    if not mentions:
        mentions.extend(_iter_regex_mentions(text))

    dedup: dict[tuple[int, int, str], CitationMention] = {}
    for mention in mentions:
        key = (mention.start_char, mention.end_char, mention.normalized_text)
        dedup[key] = mention

    ordered = sorted(dedup.values(), key=lambda m: (m.start_char, m.end_char, m.normalized_text))
    return ordered
