CREATE SCHEMA IF NOT EXISTS derived;

CREATE TABLE IF NOT EXISTS derived.caselaw_nightly_case (
    id BIGSERIAL PRIMARY KEY,
    case_id TEXT NOT NULL UNIQUE,
    courtlistener_cluster_id BIGINT NOT NULL UNIQUE,
    courtlistener_opinion_id BIGINT,
    court_id TEXT NOT NULL,
    court_name TEXT,
    date_filed DATE,
    docket_number TEXT,
    case_name TEXT NOT NULL,
    case_type TEXT NOT NULL,
    taxonomy_codes TEXT[] NOT NULL DEFAULT '{}'::text[],
    taxonomy_version TEXT NOT NULL,
    frontmatter_yaml TEXT NOT NULL,
    frontmatter_json JSONB NOT NULL,
    opinion_text TEXT,
    opinion_text_sha256 TEXT,
    source_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    first_ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS caselaw_nightly_case_date_idx
    ON derived.caselaw_nightly_case (date_filed DESC);

CREATE INDEX IF NOT EXISTS caselaw_nightly_case_court_idx
    ON derived.caselaw_nightly_case (court_id, date_filed DESC);

CREATE INDEX IF NOT EXISTS caselaw_nightly_case_type_idx
    ON derived.caselaw_nightly_case (case_type);

CREATE INDEX IF NOT EXISTS caselaw_nightly_case_taxonomy_gin
    ON derived.caselaw_nightly_case USING GIN (taxonomy_codes);

CREATE TABLE IF NOT EXISTS derived.caselaw_nightly_state (
    state_key TEXT PRIMARY KEY,
    backfill_cursor_date DATE NOT NULL,
    backfill_court_index INTEGER NOT NULL DEFAULT 0,
    last_run_started_at TIMESTAMPTZ,
    last_run_finished_at TIMESTAMPTZ,
    last_run_status TEXT,
    last_run_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS derived.taxonomy_node (
    id BIGSERIAL PRIMARY KEY,
    code TEXT NOT NULL,
    version TEXT NOT NULL,
    label TEXT NOT NULL,
    parent_code TEXT NULL,
    synonyms JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    deprecated_at TIMESTAMPTZ NULL,
    replaced_by_code TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (code, version),
    CHECK (status IN ('ACTIVE', 'DEPRECATED', 'EXPERIMENTAL'))
);

CREATE INDEX IF NOT EXISTS taxonomy_node_version_idx
    ON derived.taxonomy_node (version, code);

CREATE TABLE IF NOT EXISTS derived.legal_unit (
    id BIGSERIAL PRIMARY KEY,
    unit_id UUID NOT NULL UNIQUE,
    unit_type TEXT NOT NULL,
    taxonomy_code TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    circuit TEXT NOT NULL,
    court_level TEXT,
    year INTEGER NOT NULL,
    posture TEXT NOT NULL,
    standard_of_review TEXT NOT NULL,
    burden TEXT NOT NULL,
    is_holding BOOLEAN NOT NULL,
    is_dicta BOOLEAN NOT NULL,
    favorability INTEGER NOT NULL DEFAULT 0,
    authority_weight INTEGER NOT NULL DEFAULT 0,
    secondary_taxonomy_ids TEXT[] NOT NULL DEFAULT '{}'::text[],
    standard_unit_ids UUID[] NOT NULL DEFAULT '{}'::uuid[],
    unit_text TEXT NOT NULL,
    source_opinion_id BIGINT NOT NULL,
    ingestion_batch_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS legal_unit_taxonomy_idx
    ON derived.legal_unit (taxonomy_version, taxonomy_code);

CREATE INDEX IF NOT EXISTS legal_unit_circuit_year_idx
    ON derived.legal_unit (circuit, year DESC);

CREATE INDEX IF NOT EXISTS legal_unit_source_idx
    ON derived.legal_unit (source_opinion_id);

CREATE INDEX IF NOT EXISTS legal_unit_secondary_taxonomy_gin
    ON derived.legal_unit USING GIN (secondary_taxonomy_ids);

CREATE TABLE IF NOT EXISTS derived.job_run (
    job_name TEXT PRIMARY KEY,
    last_raw_id BIGINT NOT NULL DEFAULT 0,
    batch_size INTEGER NOT NULL DEFAULT 25,
    last_run_at TIMESTAMPTZ,
    last_status TEXT,
    last_error TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
