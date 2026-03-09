ALTER TABLE derived.legal_unit
    ADD COLUMN IF NOT EXISTS ingestion_batch_id TEXT,
    ADD COLUMN IF NOT EXISTS standard_unit_ids UUID[] NOT NULL DEFAULT '{}'::uuid[];

CREATE TABLE IF NOT EXISTS derived.ingestion_error_event (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_opinion_id BIGINT NOT NULL,
    ingestion_batch_id TEXT,
    reason TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ingestion_error_event_created_at_idx
    ON derived.ingestion_error_event (created_at);

CREATE INDEX IF NOT EXISTS ingestion_error_event_opinion_idx
    ON derived.ingestion_error_event (source_opinion_id);
