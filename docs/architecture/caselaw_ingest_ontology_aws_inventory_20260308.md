# Caselaw Ingest + Ontology (AWS/Web) Inventory

Date: 2026-03-08
Scope: Current production-adjacent code paths for caselaw ingest and ontology graph generation, with emphasis on AWS/web runtime and readiness for Neo4j + nightly Pydantic validation.

## 1) Executive Summary

The repository currently has **multiple overlapping caselaw pipelines**:

1. `scripts/nightly_caselaw_ingest.py` (CourtListener API -> `derived.*` tables)
2. `ingestion_infra/*` + `scripts/load_raw_from_staging.sql` + `scripts/derive_worker.sql` (bulk/API ingest -> `staging_records`/`raw.*` -> derived legal units)
3. `trial-discovery-ai/backend/app/services/ontology.py` now read-only for caselaw graph (legacy bootstrap path removed on 2026-03-08)
4. `scripts/compile_precedent_ontology.py` and SCOTUS vault/backfill scripts (local YAML ontology workflow, largely separate from AWS web flow)

For Acquittify **web** (`trial-discovery-ai`), the active caselaw graph endpoint reads from `derived.caselaw_nightly_case` + `derived.taxonomy_node` and does not perform request-time ingestion side effects.

This overlap creates drift risk, unclear source-of-truth, and operational ambiguity for nightly extraction/validation.

## 2) Current Process (What Actually Runs)

### 2.1 Web API graph path (AWS web runtime)

- Route: `GET /matters/{matter_id}/ontology?view=caselaw`
- File: `trial-discovery-ai/backend/app/api/routes/ontology.py`
- Service: `trial-discovery-ai/backend/app/services/ontology.py::build_caselaw_ontology_graph`

Flow:
1. Checks for `derived.caselaw_nightly_case` / `derived.taxonomy_node`.
2. If missing, returns diagnostics (`reason: missing_table:derived.caselaw_nightly_case`) and does not ingest.
3. Graph output emphasizes case and taxonomy nodes/edges (`taxonomy_edge`, `taxonomy_parent`, `decided_by`).

Important: This path is now **read-only** and depends on upstream ingest jobs.

### 2.2 Nightly ingest script path (intended batch path)

- Entry: `scripts/run_nightly_caselaw_ingest.sh`
- Worker: `scripts/nightly_caselaw_ingest.py`
- Docs: `docs/caselaw_nightly_ingest.md`
- Canonical scheduler: EventBridge Scheduler -> ECS Fargate task (`deploy/terraform/scheduler.tf`)

Flow:
1. CourtListener fetch by court/date (priority `scotus`, `cafc`, then backfill).
2. Criminal/quasi-criminal classification.
3. Taxonomy assignment (`map_case_taxonomies` + fallback regex).
4. Upsert into `derived.caselaw_nightly_case` keyed by `courtlistener_cluster_id`.
5. Upsert taxonomy catalog rows into `derived.taxonomy_node`.
6. Project per-taxonomy legal units into `derived.legal_unit`.
7. Persist ingest state in `derived.caselaw_nightly_state` and summary in JSONL logs.

### 2.3 Bulk ingestion infra path (parallel stack)

- Entry: `python -m ingestion_infra.runners.main ...`
- Wrapper: `scripts/run_courtlistener_bulk_ingest.sh`
- Storage: `ingestion_infra/storage/staging_db.py`

Flow:
1. Ingest CourtListener bulk/API entities into `staging_records` and/or `raw.*`.
2. Checkpoint state in `ingestion_checkpoints` and state file.
3. Separate SQL step (`scripts/load_raw_from_staging.sql`) can promote staging records to `raw.*`.
4. Separate SQL worker (`scripts/derive_worker.sql`) derives `derived.legal_unit` with guardrails.

Important: This is a distinct ingest/derive pipeline from nightly script; both write into overlapping DB concepts.

### 2.4 Legacy desktop graph path (retired)

- Legacy graph builder: `AcquittifyElectron/main.js` (removed from active runtime)
- Remaining helper: `scripts/caselaw_db_graph.py`

Current state:
1. Desktop/Electron path is retired and not part of the canonical AWS/web deployment.
2. `scripts/caselaw_db_graph.py` remains as a transitional utility script only.

## 3) Database Objects in Play

Primary derived tables:
- `derived.caselaw_nightly_case`
- `derived.caselaw_nightly_state`
- `derived.taxonomy_node`
- `derived.legal_unit`
- `derived.job_run`
- `derived.ingestion_error_event` (guardrails migration)

Raw/staging tables:
- `staging_records`
- `ingestion_checkpoints`
- `raw.opinion_clusters`
- `raw.opinions`
- `raw.opinion_texts`

## 4) Operations Inventory

### 4.1 Runtime operations

- Web API ontology read/build:
  - `trial-discovery-ai/backend/app/services/ontology.py::build_caselaw_ontology_graph`
- Nightly ingest batch:
  - `scripts/nightly_caselaw_ingest.py`
- Bulk ingest batch:
  - `ingestion_infra/runners/main.py` (`bulk_ingest`, `api_incremental_update`)
- Derive SQL worker:
  - `scripts/derive_worker.sql`

### 4.2 Scheduling operations

- AWS schedule now provisioned in Terraform:
  - `deploy/terraform/scheduler.tf`
  - `aws_scheduler_schedule.caselaw_ingest`
- Local launchd template remains for manual local runs only:
  - `scripts/com.acquittify.caselaw-nightly.plist`

### 4.3 Operational logs/state

- `reports/caselaw_nightly_ingest.jsonl`
- `reports/caselaw_archive_backfill.jsonl`
- `reports/caselaw-nightly.launchd.out`
- `reports/caselaw-nightly.launchd.err`
- ingestion state/checkpoints (JSON + DB)

## 5) Artifact / Redundancy Assessment (for cleanup before Neo4j)

### Keep (core candidates)

1. `scripts/nightly_caselaw_ingest.py`
- Best candidate for deterministic nightly extraction baseline.
- Already has idempotent upserts and taxonomy projection.

2. `migrations/caselaw_nightly_ingest.sql` + `migrations/ingestion_guardrails.sql`
- Canonical derived schema baseline.

3. `acquittify/ontology/schemas.py` and extractor models
- Existing Pydantic footprint to extend for Neo4j extraction/validation envelope.

### Refactor/contain

1. `scripts/caselaw_db_graph.py`
- Works as transitional renderer; needs replacement or augmentation with Neo4j-backed query adapter.

### Retire or gate behind feature flags

1. `scripts/courtlistener_opinion_autoupdate.py`
- Chroma-focused ingestion path overlaps with nightly and infra pipelines.

2. `ingestion_infra/*` path OR nightly path (choose one as source-of-truth)
- Running both for same business object creates drift.

3. `scripts/load_raw_from_staging.sql` + `scripts/derive_worker.sql` (if nightly becomes sole canonical pipeline)
- Keep only if raw/staging architecture remains strategic.

4. Legacy backfills that target archived app snapshots:
- `scripts/backfill_local_caselaw_cases.py` default archive source (`_archived_apps/...`) should be explicit/manual only.

## 6) Risks Blocking Neo4j Migration

1. No single source-of-truth ingest path.
2. Different graph outputs between desktop DB graph, web API graph, and vault ontology graph.
3. Case identity policy not unified across all paths.
4. Ingest scheduling/orchestration in AWS not explicitly codified in Terraform for caselaw nightly.

## 7) Prepared Modification Plan (Next Implementation Slice)

1. Lock source-of-truth pipeline for nightly extraction.
- Recommendation: retain `scripts/nightly_caselaw_ingest.py` semantics for now.

2. Introduce explicit extraction contract (Pydantic) for nightly outputs.
- Add a nightly envelope model for `case`, `authority anchors`, `citation anchors`, taxonomy assignments, validation flags.

3. Add Neo4j schema and writer in a separate module.
- Initial labels/relations:
  - `:Case`, `:Taxonomy`, `:Constitution`, `:USCTitle`, `:CFRTitle`
  - `(:Case)-[:CITES_CASE]->(:Case)`
  - `(:Case)-[:CITES_CONSTITUTION]->(:Constitution)`
  - `(:Case)-[:CITES_USC_TITLE]->(:USCTitle)`
  - `(:Case)-[:CITES_CFR_TITLE]->(:CFRTitle)`
  - `(:Case)-[:IN_TAXONOMY]->(:Taxonomy)`

4. Completed: request-path bootstrap writes removed from web API.
 - Missing upstream data now returns diagnostics.

5. Deprecate non-canonical ingest scripts via feature flags and docs.

6. Add nightly validation report job.
- Emit validation artifacts (JSON + markdown) with row counts, unresolved anchors, duplicate IDs, and relation sparsity checks.

## 8) Immediate Actionable Candidates for First PR

1. Completed: removed request-time bootstrap path from `build_caselaw_ontology_graph`.
2. Completed: imported Neo4j schema + graph contract + Pydantic graph projection models.
3. Completed: added validation scripts for single envelope and nightly batch.
4. Next: wire nightly ingest output into validated `CaseExtractionEnvelope` generation and Neo4j upsert.
