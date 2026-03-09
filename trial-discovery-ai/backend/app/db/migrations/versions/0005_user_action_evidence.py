"""add evidence action types

Revision ID: 0005_user_action_evidence
Revises: 0004_document_identity_feedback
Create Date: 2026-02-04
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0005_user_action_evidence"
down_revision = "0004_document_identity_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE user_action_type ADD VALUE IF NOT EXISTS 'EVIDENCE_ADD'")
    op.execute("ALTER TYPE user_action_type ADD VALUE IF NOT EXISTS 'EVIDENCE_REMOVE'")


def downgrade() -> None:
    # Enum value removals are not supported without type recreation.
    pass
