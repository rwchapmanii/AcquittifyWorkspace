from sqlalchemy import Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.enums import DocumentEntityRole


class DocumentEntity(Base):
    __tablename__ = "document_entities"

    document_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), primary_key=True
    )
    entity_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id"), primary_key=True
    )
    role: Mapped[DocumentEntityRole] = mapped_column(
        Enum(DocumentEntityRole, name="document_entity_role"), nullable=False
    )
    confidence: Mapped[float | None] = mapped_column(nullable=True)
