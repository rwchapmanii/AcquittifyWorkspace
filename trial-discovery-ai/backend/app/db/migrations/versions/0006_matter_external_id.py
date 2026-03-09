"""add matter external id

Revision ID: 0006_matter_external_id
Revises: 0005_user_action_evidence
Create Date: 2026-02-04
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0006_matter_external_id"
down_revision = "0005_user_action_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE matters ADD COLUMN IF NOT EXISTS external_id text")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_matters_external_id
            ON matters (external_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_matters_external_id")
    op.execute("ALTER TABLE matters DROP COLUMN IF EXISTS external_id")
