# Caselaw Neo4j Cutover Backlog

Date: 2026-03-08
Status: in_progress

## Phase 1: Stabilize Current Runtime

1. Completed: remove request-path bootstrap from `trial-discovery-ai/backend/app/services/ontology.py`.
2. Completed: add diagnostics in ontology API metadata when derived tables are empty (no implicit writes).
3. Mark overlapping scripts as deprecated in headers and docs:
- `scripts/courtlistener_opinion_autoupdate.py`
- `ingestion_infra/runners/main.py` (if not canonical)

## Phase 2: Pydantic Nightly Contract

1. Completed: import Pydantic extraction/graph projection models:
- `CaseExtraction`
- `CaseExtractionEnvelope`
- `GraphDocument` / `GraphNodeUpsert` / `GraphRelationshipUpsert`
2. Completed: add validator scripts:
- duplicate case IDs
- unresolved citation anchor rate
- missing taxonomy rate
- sparse-edge outliers
3. Next: emit validation artifacts nightly (JSON + markdown) under `reports/`.
4. Completed: autonomy policy + decision gate integrated (`evaluate_ontology_autonomy_policy.py`).

## Phase 3: Neo4j Schema + Writer

1. Completed: add graph schema module with node labels:
- `Case`, `Taxonomy`, `Constitution`, `USCTitle`, `CFRTitle`
2. Add relation emission:
- `CITES_CASE`, `CITES_CONSTITUTION`, `CITES_USC_TITLE`, `CITES_CFR_TITLE`, `IN_TAXONOMY`
3. Create deterministic upsert keys (canonical case id + authority ids).
4. Add job to publish nightly validated dataset to Neo4j.

## Phase 4: API Read Path Migration

1. Add Neo4j-backed caselaw graph query adapter.
2. Keep Postgres graph path behind feature flag for rollback.
3. Run A/B parity checks (node/edge counts + sampled case neighborhoods).

## Phase 5: Artifact Removal

1. Completed: remove request-path bootstrap inserts from web API.
2. Remove deprecated ingest path not selected as canonical.
3. Remove fallback docs and scripts that can produce conflicting derived data.

## Exit Criteria

1. One canonical nightly ingest path.
2. Nightly validation report generated and passing thresholds.
3. Web ontology graph served from Neo4j (Postgres fallback optional/flagged).
4. No runtime side-effect ingestion in request handlers.
