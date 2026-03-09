#!/usr/bin/env python3
import argparse
import json
import os
from typing import Any

import psycopg

DEFAULT_DSN = "postgresql://acquittify@localhost:5432/courtlistener"

SQL_QUERY = """
WITH intent AS (
    SELECT
    %s::text AS primary_prefix,
    %s::text[] AS secondary_prefixes,
    %s::text AS posture_filter,
    %s::int AS limit_rows
)
SELECT
    lu.unit_id,
    lu.unit_type,
    lu.taxonomy_code AS primary_taxonomy_code,
    lu.circuit,
    lu.year,
    lu.posture,
    lu.is_holding,
    lu.favorability,
    LEFT(lu.unit_text, 280) AS excerpt,
    CASE
        WHEN lu.taxonomy_code LIKE (intent.primary_prefix || '%%') THEN 2
        WHEN EXISTS (
            SELECT 1
            FROM unnest(intent.secondary_prefixes) AS sp
            WHERE lu.taxonomy_code LIKE (sp || '%%')
        ) THEN 1
        ELSE 0
    END AS match_score,
    lu.authority_weight
FROM derived.legal_unit lu
CROSS JOIN intent
WHERE (
    lu.taxonomy_code LIKE (intent.primary_prefix || '%%')
    OR EXISTS (
        SELECT 1
        FROM unnest(intent.secondary_prefixes) AS sp
        WHERE lu.taxonomy_code LIKE (sp || '%%')
    )
)
AND (
    intent.posture_filter = 'UNKNOWN'
    OR lu.posture = intent.posture_filter
)
ORDER BY
    match_score DESC,
    lu.authority_weight DESC,
    lu.is_holding DESC,
    lu.favorability DESC,
    lu.year DESC
LIMIT (SELECT limit_rows FROM intent);
"""


def build_result(intent: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"intent": intent, "results": [], "status": "EMPTY"}
    return {"intent": intent, "results": rows, "status": "OK"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Deterministic SQL retrieval")
    parser.add_argument("--intent", required=True, help="Intent JSON string")
    parser.add_argument("--limit", type=int, default=50, help="Max rows to return")
    args = parser.parse_args()

    intent = json.loads(args.intent)
    primary = intent.get("primary", {})
    secondary = intent.get("secondary", [])
    posture = intent.get("posture", "UNKNOWN")

    primary_prefix = primary.get("code")
    if not primary_prefix:
        raise SystemExit("intent.primary.code is required")

    secondary_prefixes = [item.get("code") for item in secondary if item.get("code")]

    params = (
        primary_prefix,
        secondary_prefixes,
        posture,
        args.limit,
    )

    dsn = os.getenv("COURTLISTENER_DB_DSN") or os.getenv("RETRIEVAL_DB_DSN") or DEFAULT_DSN

    with psycopg.connect(dsn) as conn:
        with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(SQL_QUERY, params)
            rows = cur.fetchall()

    result = build_result(intent, rows)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
