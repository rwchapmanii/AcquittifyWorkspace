"""Semantic and structural chunking for legal text."""

from __future__ import annotations

from typing import Iterable, List, Tuple

from ingestion_agent.models.chunk import Chunk
from ingestion_agent.models.metadata import Metadata
from ingestion_agent.utils.text import split_paragraphs


def chunk_sections(
    sections: Iterable[Tuple[str, str]],
    base_metadata: Metadata,
    max_chars: int,
    min_chars: int,
    overlap_paragraphs: int,
) -> List[Chunk]:
    """Chunk text using section boundaries and paragraph semantics."""
    chunks: List[Chunk] = []
    for section_type, content in sections:
        paragraphs = split_paragraphs(content)
        buffer: List[str] = []
        buffer_len = 0

        def emit() -> None:
            nonlocal buffer, buffer_len
            if not buffer:
                return
            text = "\n\n".join(buffer).strip()
            if len(text) >= min_chars:
                metadata = Metadata(
                    source=base_metadata.source,
                    doc_id=base_metadata.doc_id,
                    court=base_metadata.court,
                    date_filed=base_metadata.date_filed,
                    citation=base_metadata.citation,
                    section_type=section_type,
                    docket_number=base_metadata.docket_number,
                    url=base_metadata.url,
                )
                chunks.append(Chunk(text=text, metadata=metadata))
            buffer = []
            buffer_len = 0

        for paragraph in paragraphs:
            if not paragraph:
                continue
            if buffer_len + len(paragraph) > max_chars and buffer:
                emit()
                if overlap_paragraphs > 0:
                    buffer = buffer[-overlap_paragraphs:]
                    buffer_len = sum(len(p) for p in buffer)
            buffer.append(paragraph)
            buffer_len += len(paragraph)

        emit()
    return chunks
