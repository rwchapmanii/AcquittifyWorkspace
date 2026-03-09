CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE IF NOT EXISTS raw.opinions (
    id BIGINT PRIMARY KEY,
    cluster_id BIGINT,
    plain_text TEXT,
    opinion_text TEXT,
    html_with_citations TEXT,
    html TEXT,
    date_created TIMESTAMPTZ,
    record_json JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS opinions_cluster_id_idx ON raw.opinions (cluster_id);
CREATE INDEX IF NOT EXISTS opinions_date_created_idx ON raw.opinions (date_created);

CREATE TABLE IF NOT EXISTS raw.opinion_clusters (
    id BIGINT PRIMARY KEY,
    date_filed DATE,
    court_id BIGINT,
    record_json JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS opinion_clusters_court_id_idx ON raw.opinion_clusters (court_id);
CREATE INDEX IF NOT EXISTS opinion_clusters_date_filed_idx ON raw.opinion_clusters (date_filed);
