"""set embedding dimension to 768

Revision ID: 0004_embedding_dim_768
Revises: 0003_document_metadata_overrides
Create Date: 2026-02-03
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0004_embedding_dim_768"
down_revision = "0003_document_metadata_overrides"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE chunks
        ALTER COLUMN embedding TYPE vector(768)
        USING NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE chunks
        ALTER COLUMN embedding TYPE vector(3072)
        USING NULL
        """
    )