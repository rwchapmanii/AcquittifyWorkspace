import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.artifact import Artifact
from app.db.models.chunk import Chunk
from app.db.models.document import Document
from app.db.models.enums import ArtifactKind, DocumentStatus
from app.services.chunking import chunk_text
from app.services.embedding import embed_text
from app.services.embedding_context import (
    augment_for_embedding,
    build_embedding_context,
)
from app.storage.s3 import S3Client


def chunk_and_embed_document(*, session: Session, document_id: str) -> int:
    document = session.get(Document, document_id)
    if not document:
        raise ValueError("Document not found")

    artifact = (
        session.execute(
            select(Artifact)
            .where(
                Artifact.document_id == document_id,
                Artifact.kind == ArtifactKind.EXTRACTED_TEXT,
            )
            .order_by(Artifact.created_at.desc())
        )
        .scalars()
        .first()
    )

    if not artifact:
        raise ValueError("Extracted text artifact not found")

    s3 = S3Client()
    extracted = _load_json(s3, artifact.uri)
    chunks_created = 0
    context = build_embedding_context(document, extracted)

    if context.summary:
        summary_embedding = embed_text(
            augment_for_embedding(context.header, context.summary)
        ).vector
        summary_chunk = Chunk(
            document_id=document_id,
            page_num=None,
            chunk_index=-1,
            text=context.summary,
            start_offset=None,
            end_offset=None,
            embedding=summary_embedding,
        )
        session.add(summary_chunk)
        chunks_created += 1

    for page in extracted.get("pages", []):
        page_num = page.get("page_num")
        text = page.get("text") or ""
        for chunk_index, chunk_spec in enumerate(chunk_text(text)):
            embedding = embed_text(
                augment_for_embedding(context.header, chunk_spec.text)
            ).vector
            chunk = Chunk(
                document_id=document_id,
                page_num=page_num,
                chunk_index=chunk_index,
                text=chunk_spec.text,
                start_offset=chunk_spec.start_offset,
                end_offset=chunk_spec.end_offset,
                embedding=embedding,
            )
            session.add(chunk)
            chunks_created += 1

    document.status = DocumentStatus.INDEXED
    session.commit()
    return chunks_created


def _load_json(s3: S3Client, uri: str) -> dict:
    if not uri.startswith("s3://"):
        raise ValueError("Invalid S3 URI")
    parts = uri.replace("s3://", "", 1).split("/", 1)
    bucket = parts[0]
    key = parts[1]
    data = s3.get_bytes(bucket=bucket, key=key).decode("utf-8")
    return json.loads(data)
