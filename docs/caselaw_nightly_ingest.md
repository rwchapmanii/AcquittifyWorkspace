# Nightly Federal Criminal Caselaw Ingest

This pipeline ingests federal criminal decisions from CourtListener into Postgres (recommended: AWS RDS), applies Acquittify taxonomy codes, stores YAML frontmatter, and projects ontology nodes for graph retrieval.

## What it does

1. Ingests today's `scotus` decisions first.
2. Ingests today's `cafc` (Federal Circuit) decisions second.
3. Works backward by date across federal courts for the rest of the runtime window.
4. Enforces idempotency with an upsert keyed by `courtlistener_cluster_id`.
5. Stores:
   - `taxonomy_codes` (`TEXT[]`, indexed with GIN)
   - `frontmatter_json` (`JSONB`)
   - `frontmatter_yaml` (`TEXT`)
   - `opinion_text` and source payloads.
6. Builds ontology graph rows:
   - taxonomy catalog in `derived.taxonomy_node`
   - per-case legal units in `derived.legal_unit` (one row per assigned taxonomy code)

## Runtime window

Recommended scheduler profile for backfill and steady state:

- Schedule: `rate(30 minutes)`
- Runtime per task: `--max-runtime-hours 0.33` (about 20 minutes)

This avoids overlapping ECS tasks while continuously advancing the cursor.

## Required environment

- `ACQ_CASELAW_DB_DSN` (or `COURTLISTENER_DB_DSN`)
  - Use your AWS Postgres/RDS DSN.
- `COURTLISTENER_API_TOKEN`
  - Required to fetch opinion detail text from CourtListener opinion endpoints.

Optional:

- `ACQ_CASELAW_RUNTIME_HOURS` (default `0.33` in ECS scheduler job)
- `ACQ_CASELAW_TIMEZONE` (default `America/Detroit`)
- `ACQ_CASELAW_BACKFILL_START_DATE` (YYYY-MM-DD)
- `ACQ_CASELAW_ONLY_COURTS` (comma-separated court ids)
- `ACQ_CASELAW_LOG_PATH` (default `reports/caselaw_nightly_ingest.jsonl`)
- `ACQ_CASELAW_REQUEST_RETRIES` (default `5`)
- `ACQ_CASELAW_MAX_COURT_DATE_QUERIES` (default `0`, unlimited)
- `ACQ_CASELAW_PYTHON` (optional python executable override, e.g. `python3`)
- `ACQ_NEO4J_VALIDATION_INPUT_DIR` (optional; run Neo4j extraction validation after ingest)
- `ACQ_NEO4J_VALIDATION_GLOB` (default `**/*.*`)
- `ACQ_NEO4J_VALIDATION_JSON` (default `reports/nightly_neo4j_extraction_validation.json`)
- `ACQ_NEO4J_VALIDATION_MD` (default `reports/nightly_neo4j_extraction_validation.md`)
- `ACQ_ONTOLOGY_AUTONOMY_POLICY` (default `acquittify/ontology/neo4j/policies/acquittify_autonomy_policy_v1_2026-03-08.yaml`)
- `ACQ_ONTOLOGY_AUTONOMY_JSON` (default `reports/nightly_ontology_autonomy_decision.json`)
- `ACQ_ONTOLOGY_AUTONOMY_MD` (default `reports/nightly_ontology_autonomy_decision.md`)

## Run once

```bash
./scripts/run_nightly_caselaw_ingest.sh
```

The same command can be run manually anytime; nightly scheduling is just orchestration.
If validation input is configured, the wrapper also evaluates the autonomy policy against validation metrics.

## Run directly

```bash
python3 scripts/nightly_caselaw_ingest.py \
  --db-dsn "$ACQ_CASELAW_DB_DSN" \
  --courtlistener-token "$COURTLISTENER_API_TOKEN" \
  --max-runtime-hours 6
```

## Backfill archived local cases

```bash
python3 scripts/backfill_local_caselaw_cases.py \
  --db-dsn "$ACQ_CASELAW_DB_DSN" \
  --cases-dir "_archived_apps/acquittify_20260303_131259/acquittifystorage/corpus/cases/Federal Criminal Cases"
```

Use `--skip-taxonomy-map` for a faster regex/frontmatter taxonomy scan when importing very large archives.

## Scheduler (AWS EventBridge)

Canonical production scheduling is EventBridge Scheduler invoking ECS Fargate.

Terraform resources:

- `deploy/terraform/scheduler.tf`
- `deploy/terraform/aws_ecs_task_definition.caselaw_ingest`

Enable and tune with:

- `caselaw_scheduler_enabled`
- `caselaw_schedule_expression`
- `caselaw_job_max_runtime_hours`

Local `launchd` is deprecated for production.

## Schema migration

Apply:

- `migrations/caselaw_nightly_ingest.sql`

The runtime also self-initializes these tables if they do not exist:
- `derived.caselaw_nightly_case`
- `derived.caselaw_nightly_state`
- `derived.taxonomy_node`
- `derived.legal_unit`

## Fast retrieval examples

```sql
-- Latest criminal cases for SCOTUS
SELECT case_name, date_filed, taxonomy_codes
FROM derived.caselaw_nightly_case
WHERE court_id = 'scotus' AND case_type = 'criminal'
ORDER BY date_filed DESC
LIMIT 50;

-- Cases tagged to a taxonomy code
SELECT case_name, date_filed, court_id
FROM derived.caselaw_nightly_case
WHERE taxonomy_codes @> ARRAY['SENT.GUIDE.GEN.GEN']::text[]
ORDER BY date_filed DESC
LIMIT 100;

-- Ontology node counts (what AWS ontology graph uses)
SELECT taxonomy_version, COUNT(*) AS unit_count
FROM derived.legal_unit
GROUP BY taxonomy_version
ORDER BY taxonomy_version DESC;
```
