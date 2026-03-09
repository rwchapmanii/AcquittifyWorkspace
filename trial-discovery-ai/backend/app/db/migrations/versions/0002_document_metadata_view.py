"""create document ingestion metadata view

Revision ID: 0002_document_metadata_view
Revises: 0001_initial
Create Date: 2026-02-03
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0002_document_metadata_view"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS derived")
    op.execute(
        """
        CREATE OR REPLACE VIEW derived.document_ingestion_metadata AS
        SELECT
            d.id AS document_id,
            d.matter_id,
            d.original_filename,
            d.mime_type,
            d.sha256,
            d.file_size,
            d.page_count,
            d.ingested_at,
            d.status,
            p1.output_json AS pass1_metadata,
            p2.output_json AS pass2_metadata,
            p4.output_json AS pass4_metadata
        FROM documents d
        LEFT JOIN pass_runs p1
            ON p1.document_id = d.id
            AND p1.pass_num = 1
            AND p1.is_latest = TRUE
        LEFT JOIN pass_runs p2
            ON p2.document_id = d.id
            AND p2.pass_num = 2
            AND p2.is_latest = TRUE
        LEFT JOIN pass_runs p4
            ON p4.document_id = d.id
            AND p4.pass_num = 4
            AND p4.is_latest = TRUE
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS derived.document_ingestion_metadata")