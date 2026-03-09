"""add membership role constraint and password reset tokens

Revision ID: 0009_rbac_password_reset
Revises: 0008_merge_heads
Create Date: 2026-02-19 22:15:00.000000
"""

from alembic import op

revision = "0009_rbac_password_reset"
down_revision = "0008_merge_heads"
branch_labels = None
depends_on = None


VALID_ROLES_SQL = "('owner','admin','editor','viewer')"


def upgrade() -> None:
    op.execute("UPDATE memberships SET role = lower(role) WHERE role IS NOT NULL")
    op.execute(
        f"""
        UPDATE memberships
        SET role = 'viewer'
        WHERE role IS NULL OR role NOT IN {VALID_ROLES_SQL}
        """
    )

    op.execute("ALTER TABLE memberships DROP CONSTRAINT IF EXISTS ck_memberships_role_valid")
    op.execute(
        f"""
        ALTER TABLE memberships
        ADD CONSTRAINT ck_memberships_role_valid
        CHECK (role IN {VALID_ROLES_SQL})
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash varchar(128) NOT NULL,
            expires_at timestamptz NOT NULL,
            consumed_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_password_reset_tokens_token_hash
            ON password_reset_tokens (token_hash)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_password_reset_tokens_user_id
            ON password_reset_tokens (user_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_password_reset_tokens_user_id")
    op.execute("DROP INDEX IF EXISTS ix_password_reset_tokens_token_hash")
    op.execute("DROP TABLE IF EXISTS password_reset_tokens")
    op.execute("ALTER TABLE memberships DROP CONSTRAINT IF EXISTS ck_memberships_role_valid")
