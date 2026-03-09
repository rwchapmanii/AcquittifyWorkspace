from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import text

from app.db.base import Base
from app.db.models.enums import PassStatus


class PassRun(Base):
    __tablename__ = "pass_runs"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False
    )
    pass_num: Mapped[int] = mapped_column(Integer, nullable=False)
    model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    settings_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    input_artifact_hashes_json: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )
    output_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[PassStatus] = mapped_column(
        Enum(PassStatus, name="pass_status"), nullable=False
    )
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    is_latest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
