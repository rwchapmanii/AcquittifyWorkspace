from __future__ import annotations

import os
import re
from typing import Dict, List, Tuple

from .config import CHUNK_MIN_CHARS, CHUNK_OVERLAP_RATIO, CHUNK_SIZE_CHARS

_HEADER_PATTERNS = [
    r"^\s*UNITED STATES COURT OF APPEALS",
    r"^\s*UNITED STATES DISTRICT COURT",
    r"^\s*SUPREME COURT OF THE UNITED STATES",
    r"^\s*IN THE (SUPREME|UNITED STATES|COURT)",
    r"^\s*TABLE OF CONTENTS",
    r"^\s*TABLE OF AUTHORITIES",
    r"^\s*INDEX",
    r"^\s*Filed:\s*",
    r"^\s*No\.\s*\d",
    r"^\s*Case No\.\s*",
    r"^\s*Appeal No\.\s*",
    r"^\s*Page \d+ of \d+",
]

_CITATION_PATTERN = re.compile(
    r"(?:\bF\.?\s?\d+d|\bF\.?\s?Supp\.?\s?\d*d?|\bU\.S\.|\bS\.?\s?Ct\.|\bL\.?\s?Ed\.|"
    r"\bN\.E\.\d+d|\bP\.\d+d|\bCal\.?\s?App\.?\s?\d+d)"
)
_RULE_PATTERN = re.compile(r"(?:Fed\.\s+R\.|Rule\s+\d+|U\.S\.C\.|§\s*\d+)")
_ENTITY_PATTERN = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,}\b")


def _normalize_text(text: str) -> str:
    text = (text or "").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _split_sentences(text: str) -> List[str]:
    if not text:
        return []
    # Basic sentence splitter that tries to preserve citations reasonably well.
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
    cleaned = []
    for sent in sentences:
        sent = " ".join(sent.strip().split())
        if sent:
            cleaned.append(sent)
    return cleaned


def _looks_like_toc(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 5:
        return False
    leader_lines = 0
    for line in lines:
        if re.search(r"\.{3,}\s*\d+$", line):
            leader_lines += 1
    return leader_lines / max(len(lines), 1) >= 0.3


def _is_header_noise(text: str) -> bool:
    head = (text or "").strip().splitlines()
    first_line = head[0] if head else ""
    for pat in _HEADER_PATTERNS:
        if re.search(pat, first_line, flags=re.IGNORECASE):
            return True
    if _looks_like_toc(text):
        return True
    return False


def _has_legal_signal(text: str) -> bool:
    if _CITATION_PATTERN.search(text):
        return True
    if _RULE_PATTERN.search(text):
        return True
    if _ENTITY_PATTERN.search(text):
        return True
    return False


def _should_keep_chunk(chunk: str, full_text_len: int) -> bool:
    if not chunk:
        return False
    if len(chunk) < CHUNK_MIN_CHARS and full_text_len > CHUNK_MIN_CHARS:
        return False
    if _is_header_noise(chunk):
        return False
    if not _has_legal_signal(chunk):
        return False
    return True


def _should_keep_chunk_override(
    chunk: str,
    full_text_len: int,
    min_chars_override: int | None = None,
    allow_no_signal: bool = False,
) -> bool:
    if not chunk:
        return False
    min_chars = CHUNK_MIN_CHARS if min_chars_override is None else max(0, int(min_chars_override))
    if len(chunk) < min_chars and full_text_len > min_chars:
        return False
    if _is_header_noise(chunk):
        return False
    if not allow_no_signal and not _has_legal_signal(chunk):
        return False
    return True


def _overlap_sentences(sentences: List[str], overlap_chars: int) -> List[str]:
    if not sentences or overlap_chars <= 0:
        return []
    overlap: List[str] = []
    total = 0
    for sent in reversed(sentences):
        overlap.insert(0, sent)
        total += len(sent) + 1
        if total >= overlap_chars:
            break
    return overlap


def _split_long_sentence(sentence: str, max_chars: int) -> List[str]:
    parts = []
    start = 0
    while start < len(sentence):
        end = min(start + max_chars, len(sentence))
        parts.append(sentence[start:end].strip())
        if end >= len(sentence):
            break
        start = end
    return [p for p in parts if p]


def _chunk_sentences(
    sentences: List[str],
    full_text_len: int,
    min_chars_override: int | None = None,
    allow_no_signal: bool = False,
) -> List[str]:
    overlap_chars = max(0, int(CHUNK_SIZE_CHARS * CHUNK_OVERLAP_RATIO))
    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for sent in sentences:
        if not sent:
            continue
        if len(sent) > CHUNK_SIZE_CHARS * 1.5:
            if current:
                chunk = " ".join(current).strip()
                if _should_keep_chunk_override(chunk, full_text_len, min_chars_override, allow_no_signal):
                    chunks.append(chunk)
                current = _overlap_sentences(current, overlap_chars)
                current_len = sum(len(s) + 1 for s in current)
            for part in _split_long_sentence(sent, CHUNK_SIZE_CHARS):
                if _should_keep_chunk_override(part, full_text_len, min_chars_override, allow_no_signal):
                    chunks.append(part)
            continue

        projected = current_len + len(sent) + (1 if current else 0)
        if projected <= CHUNK_SIZE_CHARS or not current:
            current.append(sent)
            current_len = projected
            continue

        chunk = " ".join(current).strip()
        if _should_keep_chunk_override(chunk, full_text_len, min_chars_override, allow_no_signal):
            chunks.append(chunk)
        current = _overlap_sentences(current, overlap_chars)
        current_len = sum(len(s) + 1 for s in current)

        projected = current_len + len(sent) + (1 if current else 0)
        if projected > CHUNK_SIZE_CHARS and current:
            current = [sent]
            current_len = len(sent)
        else:
            current.append(sent)
            current_len = projected

    if current:
        chunk = " ".join(current).strip()
        if _should_keep_chunk_override(chunk, full_text_len, min_chars_override, allow_no_signal):
            chunks.append(chunk)

    return chunks


def chunk_text(text: str) -> List[str]:
    if os.getenv("ACQ_SECTION_CHUNKING") == "1":
        return chunk_text_sections(text)
    cleaned = _normalize_text(text)
    if not cleaned:
        return []

    sentences = _split_sentences(cleaned)
    if not sentences:
        sentences = [cleaned]
    return _chunk_sentences(sentences, len(cleaned))


def _sentence_offsets(text: str, sentences: List[str]) -> List[Tuple[int, int]]:
    offsets: List[Tuple[int, int]] = []
    cursor = 0
    for sent in sentences:
        if not sent:
            continue
        idx = text.find(sent, cursor)
        if idx < 0:
            idx = text.find(sent)
        if idx < 0:
            idx = cursor
        end = idx + len(sent)
        offsets.append((idx, end))
        cursor = end
    return offsets


def chunk_text_with_offsets(text: str) -> List[Dict]:
    cleaned = _normalize_text(text)
    if not cleaned:
        return []

    sentences = _split_sentences(cleaned)
    if not sentences:
        sentences = [cleaned]
    offsets = _sentence_offsets(cleaned, sentences)

    overlap_chars = max(0, int(CHUNK_SIZE_CHARS * CHUNK_OVERLAP_RATIO))
    chunks: List[Dict] = []
    current: List[str] = []
    current_idx: List[int] = []
    current_len = 0

    for idx, sent in enumerate(sentences):
        if not sent:
            continue
        if len(sent) > CHUNK_SIZE_CHARS * 1.5:
            if current:
                chunk = " ".join(current).strip()
                if _should_keep_chunk(chunk, len(cleaned)):
                    char_start = offsets[current_idx[0]][0]
                    char_end = offsets[current_idx[-1]][1]
                    chunks.append({"text": chunk, "char_start": char_start, "char_end": char_end})
                current = _overlap_sentences(current, overlap_chars)
                if current:
                    current_idx = current_idx[-len(current):]
                else:
                    current_idx = []
                current_len = sum(len(s) + 1 for s in current)
            sent_start, _ = offsets[idx]
            for part in _split_long_sentence(sent, CHUNK_SIZE_CHARS):
                if _should_keep_chunk(part, len(cleaned)):
                    part_start = cleaned.find(part, sent_start)
                    if part_start < 0:
                        part_start = sent_start
                    chunks.append({"text": part, "char_start": part_start, "char_end": part_start + len(part)})
            continue

        projected = current_len + len(sent) + (1 if current else 0)
        if projected <= CHUNK_SIZE_CHARS or not current:
            current.append(sent)
            current_idx.append(idx)
            current_len = projected
            continue

        chunk = " ".join(current).strip()
        if _should_keep_chunk(chunk, len(cleaned)):
            char_start = offsets[current_idx[0]][0]
            char_end = offsets[current_idx[-1]][1]
            chunks.append({"text": chunk, "char_start": char_start, "char_end": char_end})
        current = _overlap_sentences(current, overlap_chars)
        if current:
            current_idx = current_idx[-len(current):]
        else:
            current_idx = []
        current_len = sum(len(s) + 1 for s in current)

        projected = current_len + len(sent) + (1 if current else 0)
        if projected > CHUNK_SIZE_CHARS and current:
            current = [sent]
            current_idx = [idx]
            current_len = len(sent)
        else:
            current.append(sent)
            current_idx.append(idx)
            current_len = projected

    if current:
        chunk = " ".join(current).strip()
        if _should_keep_chunk(chunk, len(cleaned)):
            char_start = offsets[current_idx[0]][0]
            char_end = offsets[current_idx[-1]][1]
            chunks.append({"text": chunk, "char_start": char_start, "char_end": char_end})

    return chunks


def chunk_text_sections(text: str) -> List[str]:
    cleaned = _normalize_text(text)
    if not cleaned:
        return []
    try:
        from ingestion_agent.parsers.sections import parse_sections
    except Exception:
        sentences = _split_sentences(cleaned)
        if not sentences:
            sentences = [cleaned]
        return _chunk_sentences(sentences, len(cleaned))

    sections = parse_sections(cleaned)
    if not sections:
        sentences = _split_sentences(cleaned)
        if not sentences:
            sentences = [cleaned]
        return _chunk_sentences(sentences, len(cleaned))

    keep_short_labels = {"facts", "issues", "holding", "disposition"}
    results: List[str] = []
    for label, content in sections:
        section_text = (content or "").strip()
        if not section_text:
            continue
        sentences = _split_sentences(section_text)
        if not sentences:
            sentences = [section_text]
        min_override = 0 if label in keep_short_labels else None
        results.extend(_chunk_sentences(sentences, len(cleaned), min_chars_override=min_override))
    return results
