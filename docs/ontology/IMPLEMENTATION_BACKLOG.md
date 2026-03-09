# Ontology Implementation Backlog

## Completed (implemented in code)

1. Deterministic compile + idempotent writer
- `compile_precedent_ontology.py` + `VaultWriter.write_if_changed`
- Regression coverage: `tests/ontology/test_compile_smoke.py`

2. Citation extraction + resolution pipeline
- Extract mentions (`citation_extract.py`)
- Resolve via CourtListener client with SQLite cache (`citation_resolver.py`)
- Classify citation roles (`citation_roles.py`)

3. Strict structured extraction contract
- Pydantic extraction envelope (`extractor.py`)
- Prompt contract for holdings/issues/relations (`prompts.py`)
- Validation tests (`tests/ontology/test_extractor_contract.py`)

4. Canonical issue mapping with citation anchoring
- Canonicalization and minimality rules (`canonicalize.py`)
- Controlling-citation preference added for doctrinal anchoring
- Coverage: `tests/ontology/test_canonicalize.py`

5. Typed precedent relations with confidence and evidence spans
- Relation typing with high-signal overrides (`relations.py`)
- Cross-case relation targeting supported via explicit `target_holding_id`
- Citation-anchored target inference when explicit target ID is omitted (`citation -> case_id -> root holding`)
- Coverage: `tests/ontology/test_relations.py`, `tests/ontology/test_compile_cross_case_relation.py`

6. Metrics engine + persisted params/events
- Holding and issue PF computation (`metrics.py`)
- Circuit-aware consensus/drift (entropy across circuit stances + drift from adverse signal mass)
- Persisted indices: `indices/params.yaml`, `indices/metrics.yaml`
- Interpretation event logs under `events/interpretations/`
- Coverage: `tests/ontology/test_metrics.py`, `tests/ontology/test_vault_writer.py`

7. Fact-dimension extraction + dimension-first normalization
- Extraction contract supports:
  - holding `fact_vector`
  - issue `required_fact_dimensions`
- Canonicalization infers and normalizes fact dimensions from issue text.
- Fact variants attach to existing doctrine/rule branches instead of creating spurious issue nodes.
- Coverage: `tests/ontology/test_extractor_contract.py`, `tests/ontology/test_canonicalize.py`, `tests/ontology/test_compile_dimension_first.py`

8. Secondary authority + source nodes
- Added `source` / `secondary` schemas and holding `source_links`.
- Compiler emits source notes under `/sources/{constitution|statutes|regs|secondary}`.
- Metrics apply source-link authority weights (including secondary `0.3`) to holding PF.
- Coverage: `tests/ontology/test_schemas.py`, `tests/ontology/test_vault_writer.py`, `tests/ontology/test_metrics.py`, `tests/ontology/test_compile_sources.py`

9. Full doctrine smoke harness (Carroll -> Ross -> Acevedo + circuits)
- Added runner script: `scripts/run_ontology_doctrine_smoketest.py`.
- Harness executes sequential ingest, validates acceptance checks A-E, and emits JSON report.
- Includes:
  - citation anchoring ratio and issue citation checks,
  - taxonomy stability checks,
  - relation plausibility checks (Ross -> Carroll, Acevedo clarifies, explicit overrule detection),
  - PF ordering and split-signal checks,
  - rerun idempotency via final vault snapshot comparison.
- Coverage: `tests/ontology/test_doctrine_smoketest_runner.py`

10. Review workflow hardening + explainability
- Compiler now enriches unresolved items with deterministic review metadata:
  - `category`
  - `severity`
  - `review_action`
  - `review_id`
  - `status`
- Added severity rollups and unresolved payload in compile output.
- Persisted metrics explainability (holding/issue/event deltas) to output + vault metrics index.
- Review checklist generation is wired to explainability snapshots.
- Coverage: `tests/ontology/test_compile_review_queue.py`, `tests/ontology/test_compile_smoke.py`, `tests/ontology/test_vault_writer.py`

11. SCOTUS vault batch-compile runner + extractor hardening
- Added SCOTUS CSV batch runner: `scripts/compile_scotus_ontology_from_csv.py`.
- Supports merits-focused filtering, per-case timeout, resume controls (`offset/limit`), and JSON summary output.
- Extraction hardening:
  - parser handles fenced JSON and mixed wrappers,
  - schema-constrained Ollama output,
  - sanitizes common malformed relation fields (confidence, evidence span),
  - compiler degrades gracefully with `extraction_unresolved` instead of aborting the run.
- Coverage: `tests/ontology/test_extractor_contract.py`, `tests/ontology/test_compile_review_queue.py`

## Next leverage steps (post-MVP hardening)

1. Local propagation for idempotent recompile updates
- Limit recomputation to affected holdings/issues (neighbors + 2 hops).

2. Automated regression expansion
- Grow doctrinal smoke datasets across at least one additional doctrine.

3. Duplicate merge tooling
- Add deterministic merge actions for near-duplicate issue nodes.
