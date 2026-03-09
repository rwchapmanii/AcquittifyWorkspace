INSERT INTO raw.opinion_clusters (
    id,
    date_filed,
    court_id,
    record_json,
    updated_at
)
SELECT
    COALESCE(NULLIF((record_json->>'id')::bigint, NULL), record_id::bigint) AS id,
    NULLIF(record_json->>'date_filed', '')::date AS date_filed,
    NULLIF(record_json->>'court_id', '')::bigint AS court_id,
    record_json,
    NOW()
FROM staging_records
WHERE entity_type = 'opinion-clusters'
ON CONFLICT (id) DO UPDATE SET
    date_filed = EXCLUDED.date_filed,
    court_id = EXCLUDED.court_id,
    record_json = EXCLUDED.record_json,
    updated_at = NOW();

INSERT INTO raw.opinions (
    id,
    cluster_id,
    plain_text,
    opinion_text,
    html_with_citations,
    html,
    date_created,
    record_json,
    updated_at
)
SELECT
    COALESCE(NULLIF((record_json->>'id')::bigint, NULL), record_id::bigint) AS id,
    NULLIF(record_json->>'cluster_id', '')::bigint AS cluster_id,
    NULLIF(record_json->>'plain_text', '') AS plain_text,
    NULLIF(record_json->>'opinion_text', '') AS opinion_text,
    NULLIF(record_json->>'html_with_citations', '') AS html_with_citations,
    NULLIF(record_json->>'html', '') AS html,
    NULLIF(record_json->>'date_created', '')::timestamptz AS date_created,
    record_json,
    NOW()
FROM staging_records
WHERE entity_type = 'opinions'
ON CONFLICT (id) DO UPDATE SET
    cluster_id = EXCLUDED.cluster_id,
    plain_text = EXCLUDED.plain_text,
    opinion_text = EXCLUDED.opinion_text,
    html_with_citations = EXCLUDED.html_with_citations,
    html = EXCLUDED.html,
    date_created = EXCLUDED.date_created,
    record_json = EXCLUDED.record_json,
    updated_at = NOW();
