from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.db.models.document import Document


@dataclass(frozen=True)
class EmbeddingContext:
    header: str
    summary: str


def build_embedding_context(document: Document, extracted: dict[str, Any]) -> EmbeddingContext:
    meta = extracted.get("meta") or {}
    stats = meta.get("text_stats") or {}
    email = meta.get("email") or {}

    header_lines: list[str] = []
    _push(header_lines, "document_id", str(document.id))
    _push(header_lines, "matter_id", str(document.matter_id))
    _push(header_lines, "filename", document.original_filename)
    _push(header_lines, "source_path", document.source_path)
    _push(header_lines, "mime_type", document.mime_type)
    _push(header_lines, "document_type", meta.get("document_type"))
    _push(header_lines, "page_count", extracted.get("page_count") or document.page_count)
    _push(header_lines, "language", stats.get("language"))
    _push(header_lines, "normalized_sha256", stats.get("normalized_sha256"))
    _push(header_lines, "simhash64", stats.get("simhash"))
    _push(header_lines, "ocr_confidence_avg", stats.get("ocr_confidence_avg"))

    if email:
        _push(header_lines, "email_subject", email.get("subject"))
        _push(header_lines, "email_from", _join_people(email.get("from")))
        _push(header_lines, "email_to", _join_people(email.get("to")))
        _push(header_lines, "email_cc", _join_people(email.get("cc")))

    summary = build_document_summary(extracted)
    header = "\n".join(header_lines)
    return EmbeddingContext(header=header, summary=summary)


def build_document_summary(extracted: dict[str, Any], max_chars: int = 1400) -> str:
    meta = extracted.get("meta") or {}
    email = meta.get("email") or {}
    lines: list[str] = []

    if email:
        subject = email.get("subject")
        if subject:
            lines.append(f"Subject: {subject}")
        sender = _join_people(email.get("from"))
        if sender:
            lines.append(f"From: {sender}")
        to = _join_people(email.get("to"))
        if to:
            lines.append(f"To: {to}")

    text = "\n\n".join(page.get("text", "") for page in extracted.get("pages", []))
    if text:
        snippet = text.strip().replace("\u0000", " ")
        if len(snippet) > max_chars:
            snippet = snippet[: max_chars - 3].rstrip() + "..."
        lines.append(snippet)

    return "\n".join(lines).strip()


def augment_for_embedding(header: str, text: str) -> str:
    if not header:
        return text
    if not text:
        return header
    return f"{header}\n\n{text}"


def _push(lines: list[str], key: str, value: Any) -> None:
    if value is None:
        return
    if isinstance(value, str) and not value.strip():
        return
    lines.append(f"{key}: {value}")


def _join_people(value: Any, max_people: int = 5) -> str | None:
    if not value:
        return None
    if isinstance(value, (list, tuple)):
        people = [str(item) for item in value if item]
        if not people:
            return None
        return "; ".join(people[:max_people])
    return str(value)
