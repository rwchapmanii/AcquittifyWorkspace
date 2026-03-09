import mimetypes
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.document import Document
from app.db.models.enums import DocumentStatus
from app.db.models.matter import Matter
from app.db.models.membership import Membership
from app.services.pipelines import enqueue_document_pipeline
from app.storage.dropbox import DropboxClient, DropboxFile
from app.core.config import get_settings


class IngestResult:
    def __init__(self, created: int, skipped: int, matched: int | None = None) -> None:
        self.created = created
        self.skipped = skipped
        self.matched = matched


_CASE_STOPWORDS = {
    "v",
    "vs",
    "versus",
    "the",
    "and",
    "of",
    "in",
    "re",
    "ex",
    "parte",
    "et",
    "al",
}

_SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".eml",
    ".docx",
    ".xlsx",
    ".jpg",
    ".jpeg",
    ".png",
    ".tif",
    ".tiff",
    ".heic",
    ".heif",
    ".textclipping",
}


def _normalize_case_text(text: str) -> str:
    cleaned = text.lower()
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _tokenize_case_text(text: str) -> list[str]:
    normalized = _normalize_case_text(text)
    tokens = [t for t in normalized.split() if t and t not in _CASE_STOPWORDS]
    return tokens


def _is_supported_file(file_entry: DropboxFile) -> bool:
    return Path(file_entry.name).suffix.lower() in _SUPPORTED_EXTENSIONS


def _file_match_text(file_entry: DropboxFile) -> str:
    combined = f"{file_entry.path} {file_entry.name}"
    base = os.path.splitext(combined)[0]
    return base


def _path_matches_case(root_path: str, case_query: str) -> bool:
    if not root_path or not case_query:
        return False
    case_norm = _normalize_case_text(case_query)
    if not case_norm:
        return False
    return case_norm in _normalize_case_text(root_path)


def _match_case_files(
    *, case_query: str, files: list[DropboxFile]
) -> list[DropboxFile]:
    case_tokens = _tokenize_case_text(case_query)
    if not case_tokens:
        return []
    case_norm = " ".join(case_tokens)
    case_token_set = set(case_tokens)

    scored: list[tuple[float, DropboxFile]] = []
    for file_entry in files:
        if not _is_supported_file(file_entry):
            continue
        candidate_text = _file_match_text(file_entry)
        candidate_norm = _normalize_case_text(candidate_text)
        if not candidate_norm:
            continue

        if case_norm and case_norm in candidate_norm:
            score = 2.0
        else:
            candidate_tokens = set(_tokenize_case_text(candidate_norm))
            overlap = (
                len(candidate_tokens.intersection(case_token_set)) / len(case_token_set)
            )
            if overlap < 0.6:
                continue
            score = overlap
        scored.append((score, file_entry))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [entry for _, entry in scored]


def ingest_dropbox_folder(
    *,
    session: Session,
    matter_id: str,
    root_path: str,
    case_query: str | None = None,
) -> IngestResult:
    matter = session.get(Matter, matter_id)
    if not matter:
        raise ValueError("Matter not found")

    client = DropboxClient()
    created = 0
    skipped = 0

    settings = get_settings()
    shared_link_root = settings.dropbox_case_root_path or os.getenv("DROPBOX_CASE_ROOT_PATH", "")
    if root_path.startswith("http://") or root_path.startswith("https://"):
        files = list(client.list_files_shared_link_recursive(root_path, ""))
    elif shared_link_root.startswith("http://") or shared_link_root.startswith("https://"):
        files = list(client.list_files_shared_link_recursive(shared_link_root, root_path))
    else:
        files = list(client.list_files(root_path))

    owner_user_id: UUID | None = None
    if matter.created_by:
        try:
            owner_user_id = UUID(str(matter.created_by))
        except (TypeError, ValueError):
            owner_user_id = None
    if owner_user_id is None:
        owner_user_id = session.execute(
            select(Membership.user_id)
            .where(Membership.organization_id == matter.organization_id)
            .order_by(Membership.created_at.asc())
        ).scalar_one_or_none()
    matched_count: int | None = None
    if case_query:
        matched = _match_case_files(case_query=case_query, files=files)
        if matched:
            files = matched
            matched_count = len(matched)
        elif _path_matches_case(root_path, case_query):
            files = [f for f in files if _is_supported_file(f)]
            matched_count = len(files)
        else:
            raise ValueError(
                f"No matching case files found for query: {case_query}"
            )

    for file_entry in files:
        existing = session.execute(
            select(Document).where(
                Document.matter_id == matter_id,
                Document.source_path == file_entry.path,
            )
        ).scalar_one_or_none()

        if existing:
            skipped += 1
            continue

        mime_type, _ = mimetypes.guess_type(file_entry.name)
        document = Document(
            matter_id=matter_id,
            uploaded_by_user_id=owner_user_id,
            source_path=file_entry.path,
            original_filename=file_entry.name,
            mime_type=mime_type or "application/octet-stream",
            sha256=file_entry.content_hash or "",
            file_size=file_entry.size,
            page_count=None,
            ingested_at=datetime.now(timezone.utc),
            status=DocumentStatus.NEW,
        )
        session.add(document)
        session.flush()
        enqueue_document_pipeline(str(document.id))
        created += 1

    session.commit()
    return IngestResult(created=created, skipped=skipped, matched=matched_count)
