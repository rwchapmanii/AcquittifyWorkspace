"""add auth and tenant foundation

Revision ID: 0007_auth_tenant_foundation
Revises: 0006_matter_external_id
Create Date: 2026-02-19
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0007_auth_tenant_foundation"
down_revision = "0006_matter_external_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS organizations (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            name varchar(255) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            email varchar(320) NOT NULL,
            password_hash varchar(255) NOT NULL,
            full_name varchar(255),
            is_active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email
            ON users (email)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS memberships (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL REFERENCES organizations(id),
            user_id uuid NOT NULL REFERENCES users(id),
            role varchar(32) NOT NULL DEFAULT 'owner',
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_memberships_org_user UNIQUE (organization_id, user_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_memberships_user_id
            ON memberships (user_id)
        """
    )

    op.execute(
        """
        ALTER TABLE matters
        ADD COLUMN IF NOT EXISTS organization_id uuid
        """
    )

    op.execute(
        """
        INSERT INTO organizations (name)
        SELECT 'Legacy Organization'
        WHERE NOT EXISTS (SELECT 1 FROM organizations)
        """
    )

    op.execute(
        """
        UPDATE matters
        SET organization_id = (
            SELECT id
            FROM organizations
            ORDER BY created_at ASC
            LIMIT 1
        )
        WHERE organization_id IS NULL
        """
    )

    op.execute(
        """
        ALTER TABLE matters
        ALTER COLUMN organization_id SET NOT NULL
        """
    )
    op.execute(
        """
        ALTER TABLE matters
        DROP CONSTRAINT IF EXISTS matters_organization_id_fkey
        """
    )
    op.execute(
        """
        ALTER TABLE matters
        ADD CONSTRAINT matters_organization_id_fkey
            FOREIGN KEY (organization_id) REFERENCES organizations(id)
        """
    )

    op.execute("DROP INDEX IF EXISTS ix_matters_external_id")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_matters_organization_id
            ON matters (organization_id)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_matters_org_external_id
            ON matters (organization_id, external_id)
            WHERE external_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_matters_org_external_id")
    op.execute("DROP INDEX IF EXISTS ix_matters_organization_id")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_matters_external_id
            ON matters (external_id)
        """
    )
    op.execute(
        """
        ALTER TABLE matters
        DROP CONSTRAINT IF EXISTS matters_organization_id_fkey
        """
    )
    op.execute(
        """
        ALTER TABLE matters
        DROP COLUMN IF EXISTS organization_id
        """
    )

    op.execute("DROP TABLE IF EXISTS memberships")
    op.execute("DROP INDEX IF EXISTS ix_users_email")
    op.execute("DROP TABLE IF EXISTS users")
    op.execute("DROP TABLE IF EXISTS organizations")
