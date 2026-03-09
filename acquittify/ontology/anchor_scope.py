from __future__ import annotations

from dataclasses import dataclass
import re

from .authority_extract import AuthorityMention, extract_authority_mentions
from .citation_extract import CitationMention, extract_citation_mentions


@dataclass(frozen=True)
class SyllabusSpan:
    start_char: int
    end_char: int


_SYLLABUS_HEADER_RE = re.compile(r"(?im)^\s*syllabus\b")
_SYLLABUS_END_PATTERNS = (
    re.compile(r"(?im)^\s*opinion of the court\b"),
    re.compile(r"(?im)^\s*(?:chief\s+justice|justice|mr\.?\s+justice)\s+.+\bdelivered\s+the\s+opinion\s+of\s+the\s+court\b"),
    re.compile(r"(?im)^\s*per\s+curiam\b"),
    re.compile(r"(?im)^\s*justice\s+.+\bannounced\s+the\s+judgment\b"),
)


def find_syllabus_span(opinion_text: str, max_search_chars: int = 40000, max_syllabus_chars: int = 24000) -> SyllabusSpan | None:
    body = str(opinion_text or "")
    if not body.strip():
        return None

    search_window = body[: max(1, int(max_search_chars))]
    start_match = _SYLLABUS_HEADER_RE.search(search_window)
    if not start_match:
        return None

    start_char = int(start_match.start())
    slice_end = min(len(body), start_char + max(1, int(max_syllabus_chars)))
    syllabus_window = body[start_char:slice_end]
    end_candidates: list[int] = []
    min_offset = min(80, len(syllabus_window))
    for pattern in _SYLLABUS_END_PATTERNS:
        match = pattern.search(syllabus_window, pos=min_offset)
        if match and match.start() > 0:
            end_candidates.append(start_char + int(match.start()))

    end_char = min(end_candidates) if end_candidates else slice_end
    if end_char <= start_char:
        return None
    if (end_char - start_char) < 60:
        return None
    return SyllabusSpan(start_char=start_char, end_char=end_char)


def _offset_citation_mentions(mentions: list[CitationMention], offset: int) -> list[CitationMention]:
    if not offset:
        return list(mentions)
    shifted: list[CitationMention] = []
    for item in mentions:
        shifted.append(
            CitationMention(
                raw_text=item.raw_text,
                normalized_text=item.normalized_text,
                start_char=int(item.start_char) + int(offset),
                end_char=int(item.end_char) + int(offset),
                extractor=item.extractor,
                kind=item.kind,
            )
        )
    return shifted


def _offset_authority_mentions(mentions: list[AuthorityMention], offset: int) -> list[AuthorityMention]:
    if not offset:
        return list(mentions)
    shifted: list[AuthorityMention] = []
    for item in mentions:
        shifted.append(
            AuthorityMention(
                raw_text=item.raw_text,
                normalized_text=item.normalized_text,
                source_id=item.source_id,
                source_type=item.source_type,
                start_char=int(item.start_char) + int(offset),
                end_char=int(item.end_char) + int(offset),
                confidence=float(item.confidence),
                extractor=item.extractor,
            )
        )
    return shifted


def extract_citation_mentions_syllabus_first(
    opinion_text: str,
    *,
    full_mentions: list[CitationMention] | None = None,
    min_mentions_for_syllabus: int = 1,
) -> tuple[list[CitationMention], str, SyllabusSpan | None]:
    body = str(opinion_text or "")
    resolved_full = list(full_mentions) if full_mentions is not None else extract_citation_mentions(body)
    span = find_syllabus_span(body)
    if span is None:
        return resolved_full, "full_opinion_no_syllabus", None

    syllabus_text = body[span.start_char : span.end_char]
    syllabus_mentions = _offset_citation_mentions(extract_citation_mentions(syllabus_text), span.start_char)
    if len(syllabus_mentions) < max(1, int(min_mentions_for_syllabus)):
        return resolved_full, "full_opinion_fallback_sparse_syllabus", span
    if syllabus_mentions:
        return syllabus_mentions, "syllabus", span
    return resolved_full, "full_opinion_fallback_empty_syllabus", span


def extract_authority_mentions_syllabus_first(
    opinion_text: str,
    *,
    full_mentions: list[AuthorityMention] | None = None,
    min_mentions_for_syllabus: int = 1,
) -> tuple[list[AuthorityMention], str, SyllabusSpan | None]:
    body = str(opinion_text or "")
    resolved_full = list(full_mentions) if full_mentions is not None else extract_authority_mentions(body)
    span = find_syllabus_span(body)
    if span is None:
        return resolved_full, "full_opinion_no_syllabus", None

    syllabus_text = body[span.start_char : span.end_char]
    syllabus_mentions = _offset_authority_mentions(extract_authority_mentions(syllabus_text), span.start_char)
    if len(syllabus_mentions) < max(1, int(min_mentions_for_syllabus)):
        return resolved_full, "full_opinion_fallback_sparse_syllabus", span
    if syllabus_mentions:
        return syllabus_mentions, "syllabus", span
    return resolved_full, "full_opinion_fallback_empty_syllabus", span
