"""document metadata overrides

Revision ID: 0003_document_metadata_overrides
Revises: 0002_document_metadata_view
Create Date: 2026-02-03
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0003_document_metadata_overrides"
down_revision = "0002_document_metadata_view"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS derived")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS derived.document_metadata_overrides (
            document_id uuid PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
            pass1_override jsonb,
            pass2_override jsonb,
            pass4_override jsonb,
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )

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
            COALESCE(o.pass1_override, p1.output_json) AS pass1_metadata,
            COALESCE(o.pass2_override, p2.output_json) AS pass2_metadata,
            COALESCE(o.pass4_override, p4.output_json) AS pass4_metadata,
            o.pass1_override IS NOT NULL AS pass1_overridden,
            o.pass2_override IS NOT NULL AS pass2_overridden,
            o.pass4_override IS NOT NULL AS pass4_overridden,
            o.updated_at AS overrides_updated_at
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
        LEFT JOIN derived.document_metadata_overrides o
            ON o.document_id = d.id
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS derived.document_ingestion_metadata")
    op.execute("DROP TABLE IF EXISTS derived.document_metadata_overrides")