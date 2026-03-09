"""initial schema

Revision ID: 0001_initial
Revises: 
Create Date: 2026-02-02
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute("DROP TYPE IF EXISTS user_action_type CASCADE")
    op.execute("DROP TYPE IF EXISTS exhibit_purpose CASCADE")
    op.execute("DROP TYPE IF EXISTS document_entity_role CASCADE")
    op.execute("DROP TYPE IF EXISTS entity_type CASCADE")
    op.execute("DROP TYPE IF EXISTS pass_status CASCADE")
    op.execute("DROP TYPE IF EXISTS artifact_kind CASCADE")
    op.execute("DROP TYPE IF EXISTS document_status CASCADE")

    document_status = postgresql.ENUM(
        "NEW",
        "PREPROCESSED",
        "INDEXED",
        "READY",
        "ERROR",
        name="document_status",
        create_type=False,
    )
    artifact_kind = postgresql.ENUM(
        "PAGE_IMAGE",
        "EXTRACTED_TEXT",
        "OCR_TEXT",
        "EMAIL_JSON",
        "THUMBNAIL",
        name="artifact_kind",
        create_type=False,
    )
    pass_status = postgresql.ENUM(
        "SUCCESS",
        "FAIL",
        "REPAIRED",
        name="pass_status",
        create_type=False,
    )
    entity_type = postgresql.ENUM(
        "PERSON", "ORG", name="entity_type", create_type=False
    )
    document_entity_role = postgresql.ENUM(
        "AUTHOR",
        "SENDER",
        "RECIPIENT",
        "MENTIONED",
        "SIGNATORY",
        name="document_entity_role",
        create_type=False,
    )
    exhibit_purpose = postgresql.ENUM(
        "IMPEACHMENT",
        "TIMELINE",
        "BIAS",
        "SUBSTANTIVE",
        "FOUNDATION",
        name="exhibit_purpose",
        create_type=False,
    )
    user_action_type = postgresql.ENUM(
        "VIEW",
        "MARK_HOT",
        "UNMARK_HOT",
        "PRIORITY_OVERRIDE",
        "MARK_EXHIBIT",
        "UNMARK_EXHIBIT",
        "EXPORT",
        name="user_action_type",
        create_type=False,
    )

    document_status.create(op.get_bind(), checkfirst=True)
    artifact_kind.create(op.get_bind(), checkfirst=True)
    pass_status.create(op.get_bind(), checkfirst=True)
    entity_type.create(op.get_bind(), checkfirst=True)
    document_entity_role.create(op.get_bind(), checkfirst=True)
    exhibit_purpose.create(op.get_bind(), checkfirst=True)
    user_action_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "matters",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("dropbox_root_path", sa.Text(), nullable=True),
        sa.Column("settings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("matter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("matters.id"), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", document_status, nullable=False),
    )
    op.create_index("ix_documents_matter_id", "documents", ["matter_id"], unique=False)
    op.create_index("ix_documents_sha256", "documents", ["sha256"], unique=False)
    op.create_index("ix_documents_matter_status", "documents", ["matter_id", "status"], unique=False)

    op.create_table(
        "artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("kind", artifact_kind, nullable=False),
        sa.Column("uri", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("page_num", sa.Integer(), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=True),
        sa.Column("end_offset", sa.Integer(), nullable=True),
        sa.Column("embedding", Vector(3072), nullable=True),
    )
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"], unique=False)

    op.create_table(
        "pass_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("pass_num", sa.Integer(), nullable=False),
        sa.Column("model_id", sa.String(length=128), nullable=True),
        sa.Column("model_version", sa.String(length=128), nullable=True),
        sa.Column("prompt_id", sa.String(length=128), nullable=True),
        sa.Column("prompt_hash", sa.String(length=128), nullable=True),
        sa.Column("settings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("input_artifact_hashes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("output_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", pass_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("is_latest", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index("ix_pass_runs_doc_pass_latest", "pass_runs", ["document_id", "pass_num", "is_latest"], unique=False)
    op.create_index("ix_pass_runs_pass_latest", "pass_runs", ["pass_num", "is_latest"], unique=False)

    op.create_table(
        "entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("matter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("matters.id"), nullable=False),
        sa.Column("entity_type", entity_type, nullable=False),
        sa.Column("canonical_name", sa.String(length=255), nullable=False),
        sa.Column("aliases_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "document_entities",
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id"), primary_key=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("entities.id"), primary_key=True),
        sa.Column("role", document_entity_role, nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
    )

    op.create_table(
        "exhibits",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("matter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("matters.id"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("marked_by", sa.String(length=255), nullable=True),
        sa.Column("purpose", exhibit_purpose, nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "user_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("matter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("matters.id"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=True),
        sa.Column("action_type", user_action_type, nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("user_actions")
    op.drop_table("exhibits")
    op.drop_table("document_entities")
    op.drop_table("entities")
    op.drop_index("ix_pass_runs_pass_latest", table_name="pass_runs")
    op.drop_index("ix_pass_runs_doc_pass_latest", table_name="pass_runs")
    op.drop_table("pass_runs")
    op.drop_index("ix_chunks_document_id", table_name="chunks")
    op.drop_table("chunks")
    op.drop_table("artifacts")
    op.drop_index("ix_documents_matter_status", table_name="documents")
    op.drop_index("ix_documents_sha256", table_name="documents")
    op.drop_index("ix_documents_matter_id", table_name="documents")
    op.drop_table("documents")
    op.drop_table("matters")

    op.execute("DROP EXTENSION IF EXISTS vector")
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")

    op.execute("DROP TYPE IF EXISTS user_action_type")
    op.execute("DROP TYPE IF EXISTS exhibit_purpose")
    op.execute("DROP TYPE IF EXISTS document_entity_role")
    op.execute("DROP TYPE IF EXISTS entity_type")
    op.execute("DROP TYPE IF EXISTS pass_status")
    op.execute("DROP TYPE IF EXISTS artifact_kind")
    op.execute("DROP TYPE IF EXISTS document_status")
