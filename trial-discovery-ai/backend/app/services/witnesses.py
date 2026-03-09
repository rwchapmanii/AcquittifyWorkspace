from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.document import Document
from app.db.models.document_entity import DocumentEntity
from app.db.models.entity import Entity


@dataclass(frozen=True)
class WitnessSummary:
    id: str
    name: str
    entity_type: str
    doc_count: int


@dataclass(frozen=True)
class WitnessDocument:
    id: str
    original_filename: str
    source_path: str
    status: str


def list_witnesses(
    *, session: Session, matter_id: str, user_id: UUID | str, limit: int = 25
) -> list[WitnessSummary]:
    rows = session.execute(
        select(
            Entity.id,
            Entity.canonical_name,
            Entity.entity_type,
            func.count(DocumentEntity.document_id).label("doc_count"),
        )
        .join(DocumentEntity, DocumentEntity.entity_id == Entity.id)
        .join(Document, Document.id == DocumentEntity.document_id)
        .where(
            Entity.matter_id == matter_id,
            Document.uploaded_by_user_id == user_id,
        )
        .group_by(Entity.id)
        .order_by(func.count(DocumentEntity.document_id).desc())
        .limit(limit)
    ).all()

    return [
        WitnessSummary(
            id=str(row.id),
            name=row.canonical_name,
            entity_type=getattr(row.entity_type, "value", row.entity_type),
            doc_count=row.doc_count,
        )
        for row in rows
    ]


def list_witness_documents(
    *, session: Session, matter_id: str, entity_id: str, user_id: UUID | str
) -> list[WitnessDocument]:
    rows = session.execute(
        select(Document)
        .join(DocumentEntity, DocumentEntity.document_id == Document.id)
        .join(Entity, Entity.id == DocumentEntity.entity_id)
        .where(
            Entity.id == entity_id,
            Entity.matter_id == matter_id,
            Document.uploaded_by_user_id == user_id,
        )
        .order_by(Document.ingested_at.desc().nullslast())
    ).scalars().all()

    return [
        WitnessDocument(
            id=str(doc.id),
            original_filename=doc.original_filename,
            source_path=doc.source_path,
            status=getattr(doc.status, "value", doc.status),
        )
        for doc in rows
    ]
