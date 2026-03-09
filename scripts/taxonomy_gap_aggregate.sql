WITH base AS (
    SELECT
        fallback_code,
        domain,
        created_at,
        primary_confidence,
        input_text,
        posture,
        circuit,
        signal_phrases
    FROM derived.taxonomy_gap_event
),
agg AS (
    SELECT
        fallback_code,
        domain,
        COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '30 days') AS freq_30d,
        COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '90 days') AS freq_90d,
        COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '180 days') AS freq_180d,
        AVG(primary_confidence) AS avg_primary_confidence,
        MAX(created_at) AS last_event_at
    FROM base
    GROUP BY fallback_code, domain
),
examples AS (
    SELECT
        fallback_code,
        domain,
        ARRAY_AGG(input_text ORDER BY created_at DESC) AS inputs
    FROM base
    GROUP BY fallback_code, domain
),
phrases AS (
    SELECT
        fallback_code,
        domain,
        phrase,
        COUNT(*) AS phrase_count
    FROM base, LATERAL unnest(signal_phrases) AS phrase
    GROUP BY fallback_code, domain, phrase
),
phrase_rank AS (
    SELECT
        fallback_code,
        domain,
        phrase,
        phrase_count,
        ROW_NUMBER() OVER (PARTITION BY fallback_code, domain ORDER BY phrase_count DESC, phrase) AS rn,
        SUM(phrase_count) OVER (PARTITION BY fallback_code, domain) AS total_count
    FROM phrases
),
phrase_summary AS (
    SELECT
        fallback_code,
        domain,
        ARRAY_AGG(phrase ORDER BY phrase_count DESC, phrase) FILTER (WHERE rn <= 10) AS common_phrases,
        MAX(CASE WHEN rn = 1 THEN phrase END) AS top_phrase,
        MAX(CASE WHEN rn = 1 THEN (phrase_count::numeric / NULLIF(total_count, 0)) END) AS top_phrase_ratio
    FROM phrase_rank
    GROUP BY fallback_code, domain
),
posture_dist AS (
    SELECT
        fallback_code,
        domain,
        jsonb_object_agg(posture, cnt) AS posture_distribution,
        MAX(posture) FILTER (WHERE rn = 1) AS dominant_posture
    FROM (
        SELECT
            fallback_code,
            domain,
            COALESCE(posture, 'UNKNOWN') AS posture,
            COUNT(*) AS cnt,
            ROW_NUMBER() OVER (PARTITION BY fallback_code, domain ORDER BY COUNT(*) DESC, COALESCE(posture, 'UNKNOWN')) AS rn
        FROM base
        GROUP BY fallback_code, domain, COALESCE(posture, 'UNKNOWN')
    ) t
    GROUP BY fallback_code, domain
),
circuits AS (
    SELECT
        fallback_code,
        domain,
        ARRAY_AGG(DISTINCT circuit ORDER BY circuit) FILTER (WHERE circuit IS NOT NULL) AS circuits
    FROM base
    GROUP BY fallback_code, domain
)
INSERT INTO derived.taxonomy_review_queue (
    fallback_code,
    domain,
    freq_30d,
    freq_90d,
    freq_180d,
    avg_primary_confidence,
    representative_inputs,
    common_phrases,
    posture_distribution,
    circuits,
    dominant_posture,
    top_phrase,
    top_phrase_ratio,
    last_event_at,
    updated_at
)
SELECT
    agg.fallback_code,
    agg.domain,
    agg.freq_30d,
    agg.freq_90d,
    agg.freq_180d,
    COALESCE(agg.avg_primary_confidence, 0),
    (examples.inputs)[1:20],
    COALESCE(phrase_summary.common_phrases, ARRAY[]::text[]),
    COALESCE(posture_dist.posture_distribution, '{}'::jsonb),
    COALESCE(circuits.circuits, ARRAY[]::text[]),
    posture_dist.dominant_posture,
    phrase_summary.top_phrase,
    phrase_summary.top_phrase_ratio,
    agg.last_event_at,
    NOW()
FROM agg
LEFT JOIN examples ON examples.fallback_code = agg.fallback_code AND examples.domain = agg.domain
LEFT JOIN phrase_summary ON phrase_summary.fallback_code = agg.fallback_code AND phrase_summary.domain = agg.domain
LEFT JOIN posture_dist ON posture_dist.fallback_code = agg.fallback_code AND posture_dist.domain = agg.domain
LEFT JOIN circuits ON circuits.fallback_code = agg.fallback_code AND circuits.domain = agg.domain
ON CONFLICT (fallback_code, domain) DO UPDATE
SET freq_30d = EXCLUDED.freq_30d,
    freq_90d = EXCLUDED.freq_90d,
    freq_180d = EXCLUDED.freq_180d,
    avg_primary_confidence = EXCLUDED.avg_primary_confidence,
    representative_inputs = EXCLUDED.representative_inputs,
    common_phrases = EXCLUDED.common_phrases,
    posture_distribution = EXCLUDED.posture_distribution,
    circuits = EXCLUDED.circuits,
    dominant_posture = EXCLUDED.dominant_posture,
    top_phrase = EXCLUDED.top_phrase,
    top_phrase_ratio = EXCLUDED.top_phrase_ratio,
    last_event_at = EXCLUDED.last_event_at,
    updated_at = NOW();
