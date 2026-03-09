CREATE SCHEMA IF NOT EXISTS derived;

CREATE TABLE IF NOT EXISTS derived.taxonomy_node (
	id BIGSERIAL PRIMARY KEY,
	code TEXT NOT NULL,
	version TEXT NOT NULL,
	label TEXT NOT NULL,
	parent_code TEXT NULL,
	synonyms JSONB NOT NULL DEFAULT '[]'::jsonb,
	created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
	updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
	UNIQUE (code, version)
);

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
	unit_text TEXT NOT NULL,
	source_opinion_id BIGINT NOT NULL,
	created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
	updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS derived.job_run (
	job_name TEXT PRIMARY KEY,
	last_raw_id BIGINT NOT NULL DEFAULT 0,
	batch_size INTEGER NOT NULL DEFAULT 25,
	last_run_at TIMESTAMPTZ,
	last_status TEXT,
	last_error TEXT,
	updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
