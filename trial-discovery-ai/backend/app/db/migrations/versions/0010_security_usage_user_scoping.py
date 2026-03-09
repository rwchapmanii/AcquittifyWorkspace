"""add mfa, user usage metrics, and per-user document ownership

Revision ID: 0010_security_usage_user_scoping
Revises: 0009_rbac_password_reset
Create Date: 2026-03-06 23:30:00.000000
"""

from alembic import op

revision = "0010_security_usage_user_scoping"
down_revision = "0009_rbac_password_reset"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS mfa_enabled boolean NOT NULL DEFAULT false
        """
    )
    op.execute(
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS mfa_secret_enc text
        """
    )
    op.execute(
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS mfa_pending_secret_enc text
        """
    )
    op.execute(
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS mfa_backup_codes_hashes jsonb NOT NULL DEFAULT '[]'::jsonb
        """
    )
    op.execute(
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS mfa_enrolled_at timestamptz
        """
    )
    op.execute(
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS mfa_last_verified_at timestamptz
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_login_challenges (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            ticket_hash varchar(128) NOT NULL,
            expires_at timestamptz NOT NULL,
            consumed_at timestamptz,
            attempts integer NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_auth_login_challenges_ticket_hash
            ON auth_login_challenges (ticket_hash)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_auth_login_challenges_user_id
            ON auth_login_challenges (user_id)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_account_metrics (
            user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            total_storage_bytes bigint NOT NULL DEFAULT 0,
            total_upload_bytes bigint NOT NULL DEFAULT 0,
            total_documents bigint NOT NULL DEFAULT 0,
            total_agent_requests bigint NOT NULL DEFAULT 0,
            total_agent_prompt_tokens bigint NOT NULL DEFAULT 0,
            total_agent_completion_tokens bigint NOT NULL DEFAULT 0,
            total_agent_tokens bigint NOT NULL DEFAULT 0,
            total_logins bigint NOT NULL DEFAULT 0,
            total_password_resets bigint NOT NULL DEFAULT 0,
            last_login_at timestamptz,
            last_activity_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_user_account_metrics_organization_id
            ON user_account_metrics (organization_id)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_metric_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            matter_id uuid REFERENCES matters(id) ON DELETE SET NULL,
            document_id uuid REFERENCES documents(id) ON DELETE SET NULL,
            event_type varchar(64) NOT NULL,
            quantity bigint NOT NULL DEFAULT 0,
            metadata_json jsonb,
            note text,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_user_metric_events_user_id
            ON user_metric_events (user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_user_metric_events_org_type_created
            ON user_metric_events (organization_id, event_type, created_at)
        """
    )

    op.execute(
        """
        ALTER TABLE documents
        ADD COLUMN IF NOT EXISTS uploaded_by_user_id uuid
        """
    )
    op.execute(
        """
        UPDATE documents d
        SET uploaded_by_user_id = m.created_by::uuid
        FROM matters m
        WHERE d.matter_id = m.id
          AND d.uploaded_by_user_id IS NULL
          AND m.created_by ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
        """
    )
    op.execute(
        """
        UPDATE documents d
        SET uploaded_by_user_id = fallback.user_id
        FROM matters m
        JOIN LATERAL (
            SELECT memberships.user_id
            FROM memberships
            WHERE memberships.organization_id = m.organization_id
            ORDER BY memberships.created_at ASC
            LIMIT 1
        ) AS fallback ON true
        WHERE d.matter_id = m.id
          AND d.uploaded_by_user_id IS NULL
        """
    )
    op.execute(
        """
        ALTER TABLE documents
        DROP CONSTRAINT IF EXISTS fk_documents_uploaded_by_user
        """
    )
    op.execute(
        """
        ALTER TABLE documents
        ADD CONSTRAINT fk_documents_uploaded_by_user
            FOREIGN KEY (uploaded_by_user_id) REFERENCES users(id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_documents_uploaded_by_user_id
            ON documents (uploaded_by_user_id)
        """
    )

    op.execute("DROP VIEW IF EXISTS derived.document_ingestion_metadata")
    op.execute(
        """
        CREATE VIEW derived.document_ingestion_metadata AS
        SELECT
            d.id AS document_id,
            d.matter_id,
            d.uploaded_by_user_id,
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
    op.execute(
        """
        CREATE VIEW derived.document_ingestion_metadata AS
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

    op.execute("DROP INDEX IF EXISTS ix_documents_uploaded_by_user_id")
    op.execute(
        """
        ALTER TABLE documents
        DROP CONSTRAINT IF EXISTS fk_documents_uploaded_by_user
        """
    )
    op.execute(
        """
        ALTER TABLE documents
        DROP COLUMN IF EXISTS uploaded_by_user_id
        """
    )

    op.execute("DROP INDEX IF EXISTS ix_user_metric_events_org_type_created")
    op.execute("DROP INDEX IF EXISTS ix_user_metric_events_user_id")
    op.execute("DROP TABLE IF EXISTS user_metric_events")

    op.execute("DROP INDEX IF EXISTS ix_user_account_metrics_organization_id")
    op.execute("DROP TABLE IF EXISTS user_account_metrics")

    op.execute("DROP INDEX IF EXISTS ix_auth_login_challenges_user_id")
    op.execute("DROP INDEX IF EXISTS ix_auth_login_challenges_ticket_hash")
    op.execute("DROP TABLE IF EXISTS auth_login_challenges")

    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS mfa_last_verified_at")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS mfa_enrolled_at")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS mfa_backup_codes_hashes")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS mfa_pending_secret_enc")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS mfa_secret_enc")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS mfa_enabled")
