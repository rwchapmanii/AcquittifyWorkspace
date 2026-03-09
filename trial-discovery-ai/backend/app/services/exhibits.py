import csv
import io
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.document import Document
from app.db.models.exhibit import Exhibit


@dataclass(frozen=True)
class ExhibitRow:
    exhibit_id: str
    document_id: str
    purpose: str
    marked_by: str | None
    notes: str | None
    original_filename: str
    source_path: str


def list_exhibits(
    *, session: Session, matter_id: str, user_id: UUID | str
) -> list[ExhibitRow]:
    rows = session.execute(
        select(Exhibit, Document)
        .join(Document, Document.id == Exhibit.document_id)
        .where(
            Exhibit.matter_id == matter_id,
            Document.uploaded_by_user_id == user_id,
        )
        .order_by(Exhibit.created_at.desc())
    ).all()

    return [
        ExhibitRow(
            exhibit_id=str(exhibit.id),
            document_id=str(document.id),
            purpose=getattr(exhibit.purpose, "value", exhibit.purpose),
            marked_by=exhibit.marked_by,
            notes=exhibit.notes,
            original_filename=document.original_filename,
            source_path=document.source_path,
        )
        for exhibit, document in rows
    ]


def export_exhibits_csv(rows: list[ExhibitRow]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "exhibit_id",
            "document_id",
            "purpose",
            "marked_by",
            "notes",
            "original_filename",
            "source_path",
        ],
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(row.__dict__)
    return output.getvalue()
