"""document identity feedback

Revision ID: 0004_document_identity_feedback
Revises: 0003_document_metadata_overrides
Create Date: 2026-02-04
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0004_document_identity_feedback"
down_revision = "0003_document_metadata_overrides"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS derived")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS derived.document_identity_feedback (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            matter_id uuid NOT NULL REFERENCES matters(id) ON DELETE CASCADE,
            old_identity jsonb,
            new_identity jsonb,
            source text NOT NULL DEFAULT 'override',
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_identity_feedback_document
            ON derived.document_identity_feedback (document_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_identity_feedback_matter
            ON derived.document_identity_feedback (matter_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS derived.document_identity_feedback")
