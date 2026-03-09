CREATE TABLE IF NOT EXISTS derived.taxonomy_gap_event (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    input_text TEXT NOT NULL,
    intent_json JSONB NOT NULL,
    taxonomy_version TEXT NOT NULL,
    primary_code TEXT NOT NULL,
    primary_confidence NUMERIC NOT NULL,
    secondary_codes TEXT[] NOT NULL DEFAULT '{}'::text[],
    secondary_confidences NUMERIC[] NOT NULL DEFAULT '{}'::numeric[],
    top_candidate_code TEXT,
    top_candidate_confidence NUMERIC,
    second_candidate_code TEXT,
    second_candidate_confidence NUMERIC,
    needs_clarification BOOLEAN NOT NULL DEFAULT FALSE,
    gap_reasons TEXT[] NOT NULL DEFAULT '{}'::text[],
    fallback_code TEXT NOT NULL,
    domain TEXT NOT NULL,
    posture TEXT,
    circuit TEXT,
    signal_phrases TEXT[] NOT NULL DEFAULT '{}'::text[]
);

CREATE INDEX IF NOT EXISTS taxonomy_gap_event_created_at_idx
    ON derived.taxonomy_gap_event (created_at);

CREATE INDEX IF NOT EXISTS taxonomy_gap_event_fallback_idx
    ON derived.taxonomy_gap_event (fallback_code, domain);

CREATE TABLE IF NOT EXISTS derived.taxonomy_review_queue (
    id BIGSERIAL PRIMARY KEY,
    fallback_code TEXT NOT NULL,
    domain TEXT NOT NULL,
    freq_30d INTEGER NOT NULL,
    freq_90d INTEGER NOT NULL,
    freq_180d INTEGER NOT NULL,
    avg_primary_confidence NUMERIC NOT NULL,
    representative_inputs TEXT[] NOT NULL,
    common_phrases TEXT[] NOT NULL,
    posture_distribution JSONB NOT NULL,
    circuits TEXT[] NOT NULL,
    dominant_posture TEXT,
    top_phrase TEXT,
    top_phrase_ratio NUMERIC,
    last_event_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'NEW',
    decision_action TEXT,
    decision_by TEXT,
    decision_at TIMESTAMPTZ,
    decision_notes TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (fallback_code, domain)
);

CREATE INDEX IF NOT EXISTS taxonomy_review_queue_status_idx
    ON derived.taxonomy_review_queue (status);

ALTER TABLE derived.taxonomy_review_queue
    ADD CONSTRAINT taxonomy_review_queue_status_check
    CHECK (status IN ('NEW','UNDER_REVIEW','ACCEPTED','REJECTED','DEFERRED'));

ALTER TABLE derived.taxonomy_review_queue
    ADD CONSTRAINT taxonomy_review_queue_action_check
    CHECK (decision_action IS NULL OR decision_action IN ('ADD_NODE','ADD_SYNONYMS_ONLY','DEFER','REJECT'));
