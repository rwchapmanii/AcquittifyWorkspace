\set job_name 'derive_worker_v1'
\set batch_size 25

BEGIN;

INSERT INTO derived.job_run (job_name, last_raw_id, batch_size, updated_at)
VALUES (:'job_name', 0, :batch_size, NOW())
ON CONFLICT (job_name) DO UPDATE
SET batch_size = EXCLUDED.batch_size,
    updated_at = NOW();

WITH params AS (
    SELECT job_name, last_raw_id, batch_size
    FROM derived.job_run
    WHERE job_name = :'job_name'
),
settings AS (
    SELECT
        NULLIF(current_setting('acquittify.ingestion_batch_id', true), '') AS ingestion_batch_id,
        (COALESCE(NULLIF(current_setting('acquittify.pilot_mode', true), ''), 'false'))::boolean AS pilot_mode,
        string_to_array(NULLIF(current_setting('acquittify.pilot_circuits', true), ''), ',') AS pilot_circuits,
        NULLIF(current_setting('acquittify.pilot_year', true), '')::int AS pilot_year,
        COALESCE(NULLIF(current_setting('acquittify.pilot_max_units', true), ''), '5000')::int AS pilot_max_units,
        40::int AS max_units_per_opinion,
        5::int AS max_holdings_per_opinion
),
source AS (
    SELECT
        o.id AS opinion_id,
        o.cluster_id,
        COALESCE(o.plain_text, o.opinion_text, o.html_with_citations, o.html) AS body,
        o.date_created
    FROM raw.opinions o
    JOIN params p ON o.id > p.last_raw_id
    ORDER BY o.id
    LIMIT (SELECT batch_size FROM params)
),
clusters AS (
    SELECT oc.id AS cluster_id,
           oc.date_filed,
           oc.court_id
    FROM raw.opinion_clusters oc
),
prepared AS (
    SELECT
        s.opinion_id,
        s.body,
        COALESCE(c.court_id::text, 'UNKNOWN') AS circuit,
        EXTRACT(YEAR FROM COALESCE(c.date_filed, s.date_created, NOW()))::int AS year
    FROM source s
    LEFT JOIN clusters c ON c.cluster_id = s.cluster_id
    CROSS JOIN settings st
    WHERE NOT st.pilot_mode
       OR (
           st.pilot_year IS NOT NULL
           AND EXTRACT(YEAR FROM COALESCE(c.date_filed, s.date_created, NOW()))::int = st.pilot_year
           AND (st.pilot_circuits IS NULL OR COALESCE(c.court_id::text, 'UNKNOWN') = ANY(st.pilot_circuits))
       )
),
unit_map AS (
    SELECT 1 AS idx, 'FACT_PATTERN'::text AS unit_type
    UNION ALL
    SELECT 2, 'LEGAL_STANDARD'
    UNION ALL
    SELECT 3, 'APPLICATION'
),
unit_base AS (
    SELECT
        p.opinion_id,
        um.unit_type,
        um.idx,
        COALESCE((
            ARRAY(
                SELECT trim(x)
                FROM unnest(regexp_split_to_array(p.body, E'\\n\\s*\\n')) AS x
                WHERE length(trim(x)) > 0
            )
        )[um.idx], p.body) AS unit_text,
        p.circuit,
        p.year,
        (
            substr(md5(p.opinion_id::text || ':' || um.unit_type || ':' || um.idx::text), 1, 8) || '-' ||
            substr(md5(p.opinion_id::text || ':' || um.unit_type || ':' || um.idx::text), 9, 4) || '-' ||
            substr(md5(p.opinion_id::text || ':' || um.unit_type || ':' || um.idx::text), 13, 4) || '-' ||
            substr(md5(p.opinion_id::text || ':' || um.unit_type || ':' || um.idx::text), 17, 4) || '-' ||
            substr(md5(p.opinion_id::text || ':' || um.unit_type || ':' || um.idx::text), 21, 12)
        )::uuid AS unit_id,
        CASE WHEN lower(COALESCE((
            ARRAY(
                SELECT trim(x)
                FROM unnest(regexp_split_to_array(p.body, E'\\n\\s*\\n')) AS x
                WHERE length(trim(x)) > 0
            )
        )[um.idx], p.body)) LIKE '%we hold%' THEN TRUE ELSE FALSE END AS is_holding,
        CASE WHEN lower(COALESCE((
            ARRAY(
                SELECT trim(x)
                FROM unnest(regexp_split_to_array(p.body, E'\\n\\s*\\n')) AS x
                WHERE length(trim(x)) > 0
            )
        )[um.idx], p.body)) LIKE '%we hold%' THEN FALSE ELSE TRUE END AS is_dicta
    FROM prepared p
    CROSS JOIN unit_map um
    WHERE p.body IS NOT NULL AND length(trim(p.body)) > 0
),
standard_map AS (
    SELECT
        opinion_id,
        array_agg(unit_id) FILTER (WHERE unit_type = 'LEGAL_STANDARD') AS standard_unit_ids
    FROM unit_base
    GROUP BY opinion_id
),
unit_counts AS (
    SELECT
        opinion_id,
        COUNT(*) AS total_units,
        COUNT(*) FILTER (WHERE is_holding) AS holding_units
    FROM unit_base
    GROUP BY opinion_id
),
taxonomy_status AS (
    SELECT COALESCE(
        (SELECT status FROM derived.taxonomy_node WHERE code = '4A.SEARCH' AND version = '2026.01'),
        'ACTIVE'
    ) AS status
),
guardrail_failures AS (
    SELECT
        uc.opinion_id,
        CASE
            WHEN uc.total_units > st.max_units_per_opinion THEN 'max_units_exceeded'
            WHEN uc.holding_units > st.max_holdings_per_opinion THEN 'max_holdings_exceeded'
            WHEN uc.holding_units > 0 AND (sm.standard_unit_ids IS NULL OR array_length(sm.standard_unit_ids, 1) = 0)
                THEN 'holding_without_standard'
            WHEN ts.status = 'DEPRECATED' THEN 'deprecated_taxonomy_code'
            ELSE NULL
        END AS reason,
        uc.total_units,
        uc.holding_units,
        sm.standard_unit_ids
    FROM unit_counts uc
    LEFT JOIN standard_map sm ON sm.opinion_id = uc.opinion_id
    CROSS JOIN settings st
    CROSS JOIN taxonomy_status ts
    WHERE uc.total_units > st.max_units_per_opinion
       OR uc.holding_units > st.max_holdings_per_opinion
       OR (uc.holding_units > 0 AND (sm.standard_unit_ids IS NULL OR array_length(sm.standard_unit_ids, 1) = 0))
       OR ts.status = 'DEPRECATED'
),
record_guardrail_failures AS (
    INSERT INTO derived.ingestion_error_event (
        source_opinion_id,
        ingestion_batch_id,
        reason,
        details
    )
    SELECT
        gf.opinion_id,
        st.ingestion_batch_id,
        gf.reason,
        jsonb_build_object(
            'total_units', gf.total_units,
            'holding_units', gf.holding_units,
            'standard_unit_ids', gf.standard_unit_ids,
            'max_units_per_opinion', st.max_units_per_opinion,
            'max_holdings_per_opinion', st.max_holdings_per_opinion
        )
    FROM guardrail_failures gf
    CROSS JOIN settings st
    RETURNING source_opinion_id
),
eligible_units AS (
    SELECT
        ub.*, sm.standard_unit_ids
    FROM unit_base ub
    LEFT JOIN standard_map sm ON sm.opinion_id = ub.opinion_id
    LEFT JOIN guardrail_failures gf ON gf.opinion_id = ub.opinion_id
    WHERE gf.opinion_id IS NULL
),
batch_limits AS (
    SELECT
        st.pilot_mode,
        st.pilot_max_units,
        st.ingestion_batch_id,
        COALESCE((SELECT COUNT(*) FROM derived.legal_unit WHERE ingestion_batch_id = st.ingestion_batch_id), 0) AS existing_units
    FROM settings st
),
limited_units AS (
    SELECT eu.*
    FROM eligible_units eu
    CROSS JOIN batch_limits bl
    ORDER BY eu.opinion_id, eu.idx
    LIMIT CASE
        WHEN bl.pilot_mode THEN GREATEST(bl.pilot_max_units - bl.existing_units, 0)
        ELSE 100000000
    END
),
inserted AS (
    INSERT INTO derived.legal_unit (
        unit_id,
        unit_type,
        taxonomy_code,
        taxonomy_version,
        circuit,
        year,
        posture,
        standard_of_review,
        burden,
        is_holding,
        is_dicta,
        authority_weight,
        favorability,
        secondary_taxonomy_ids,
        standard_unit_ids,
        unit_text,
        source_opinion_id,
        ingestion_batch_id
    )
    SELECT
        unit_id,
        unit_type,
        '4A.SEARCH'::text AS taxonomy_code,
        '2026.01'::text AS taxonomy_version,
        circuit,
        year,
        'UNKNOWN'::text AS posture,
        'UNKNOWN'::text AS standard_of_review,
        'UNKNOWN'::text AS burden,
        is_holding,
        is_dicta,
        0::int AS authority_weight,
        0::int AS favorability,
        '{}'::text[] AS secondary_taxonomy_ids,
        CASE WHEN unit_type = 'HOLDING' THEN COALESCE(standard_unit_ids, '{}'::uuid[]) ELSE '{}'::uuid[] END AS standard_unit_ids,
        unit_text,
        opinion_id,
        (SELECT ingestion_batch_id FROM settings)
    FROM limited_units
    ON CONFLICT (unit_id) DO NOTHING
    RETURNING source_opinion_id
),
progress AS (
    SELECT COALESCE(MAX(opinion_id), NULL) AS max_id FROM source
)
UPDATE derived.job_run
SET last_raw_id = COALESCE((SELECT max_id FROM progress), last_raw_id),
    last_run_at = NOW(),
    last_status = CASE WHEN (SELECT COUNT(*) FROM source) = 0 THEN 'no-op' ELSE 'ok' END,
    updated_at = NOW()
WHERE job_name = :'job_name';

COMMIT;
