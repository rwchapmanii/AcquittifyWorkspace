from __future__ import annotations

from dataclasses import asdict
from typing import List, Dict, Optional

from .transcript_parser import TranscriptPage

DEFAULT_MAX_CHARS = 4000
DEFAULT_OVERLAP_CHARS = 300


def _build_citation(case_title: str | None, docket_number: str | None,
                    transcript_page: int | None, page_id: int | None) -> str:
    parts = []
    if case_title:
        if docket_number:
            parts.append(f"{case_title}, No. {docket_number}")
        else:
            parts.append(case_title)
    if transcript_page is not None:
        parts.append(f"Tr. {transcript_page}")
    if page_id is not None:
        parts.append(f"PageID {page_id}")
    return " ".join(parts).strip() + "." if parts else "Transcript citation unavailable."


def _chunk_text(text: str, max_chars: int, overlap_chars: int) -> List[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        chunk = text[start:end]
        chunks.append(chunk.strip())
        if end >= len(text):
            break
        start = max(end - overlap_chars, 0)
    return [c for c in chunks if c]


def chunk_pages(
    pages: List[TranscriptPage],
    case_title: str | None,
    docket_number: str | None,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> List[Dict]:
    chunks: List[Dict] = []
    current_group: List[TranscriptPage] = []
    current_key = None

    def flush_group(group: List[TranscriptPage]) -> None:
        if not group:
            return
        combined_text = "\n\n".join(p.text for p in group if p.text)
        chunk_texts = _chunk_text(combined_text, max_chars, overlap_chars)
        for chunk_text in chunk_texts:
            first_page = next((p for p in group if p.transcript_page or p.page_id), group[0])
            citation = _build_citation(case_title, docket_number, first_page.transcript_page, first_page.page_id)
            chunks.append({
                "case_title": case_title,
                "docket_number": docket_number,
                "document_type": "trial_transcript",
                "witness": group[0].witness,
                "exam": group[0].exam,
                "questioner": group[0].questioner,
                "transcript_page": first_page.transcript_page,
                "page_id": first_page.page_id,
                "page_start": group[0].transcript_page,
                "page_end": group[-1].transcript_page,
                "text": chunk_text,
                "citation": citation,
            })

    for page in pages:
        key = (page.witness, page.exam, page.questioner)
        if current_key is None:
            current_key = key
        if key != current_key and current_group:
            flush_group(current_group)
            current_group = []
            current_key = key
        current_group.append(page)

    if current_group:
        flush_group(current_group)

    return chunks
