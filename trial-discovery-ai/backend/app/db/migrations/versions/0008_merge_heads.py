"""merge migration heads

Revision ID: 0008_merge_heads
Revises: 0004_embedding_dim_768, 0007_auth_tenant_foundation
Create Date: 2026-02-19
"""

# revision identifiers, used by Alembic.
revision = "0008_merge_heads"
down_revision = ("0004_embedding_dim_768", "0007_auth_tenant_foundation")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
