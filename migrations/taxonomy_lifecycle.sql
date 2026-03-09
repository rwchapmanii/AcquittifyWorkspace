CREATE EXTENSION IF NOT EXISTS ltree;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'taxonomy_status') THEN
        CREATE TYPE derived.taxonomy_status AS ENUM ('ACTIVE','DEPRECATED','EXPERIMENTAL');
    END IF;
END$$;

ALTER TABLE derived.taxonomy_node
    ADD COLUMN IF NOT EXISTS status derived.taxonomy_status NOT NULL DEFAULT 'ACTIVE',
    ADD COLUMN IF NOT EXISTS deprecated_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS replaced_by_code ltree NULL;

CREATE INDEX IF NOT EXISTS taxonomy_node_status_idx
    ON derived.taxonomy_node (status);
