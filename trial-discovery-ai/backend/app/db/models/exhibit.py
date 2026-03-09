from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import text

from app.db.base import Base
from app.db.models.enums import ExhibitPurpose


class Exhibit(Base):
    __tablename__ = "exhibits"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    matter_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("matters.id"), nullable=False
    )
    document_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False
    )
    marked_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    purpose: Mapped[ExhibitPurpose] = mapped_column(
        Enum(ExhibitPurpose, name="exhibit_purpose"), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
