CREATE TABLE IF NOT EXISTS derived.admin_user (
    id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (role IN ('admin_reviewer', 'read_only'))
);

CREATE TABLE IF NOT EXISTS derived.taxonomy_review_event (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    action_type TEXT NOT NULL,
    target_code TEXT,
    target_version TEXT,
    payload JSONB NOT NULL,
    actor TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS taxonomy_review_event_created_at_idx
    ON derived.taxonomy_review_event (created_at);

CREATE TABLE IF NOT EXISTS derived.intent_audit_log (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    input_text TEXT NOT NULL,
    signals JSONB NOT NULL,
    primary_code TEXT NOT NULL,
    primary_confidence NUMERIC NOT NULL,
    secondary_codes TEXT[] NOT NULL DEFAULT '{}'::text[],
    secondary_confidences NUMERIC[] NOT NULL DEFAULT '{}'::numeric[],
    posture TEXT NOT NULL,
    posture_confidence NUMERIC NOT NULL,
    routing_plan JSONB NOT NULL,
    taxonomy_version TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS intent_audit_log_created_at_idx
    ON derived.intent_audit_log (created_at);
