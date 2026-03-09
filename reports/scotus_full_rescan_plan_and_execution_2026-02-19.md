# SCOTUS Ontology: Full Re-Scan Plan + Execution (2026-02-19)

## Objective
Perform a full corpus-wide ontology verification and re-scan for all SCOTUS cases, then enforce graph connectivity so every case has at least one ontology link in graph view.

## Corpus Scope
- SCOTUS case notes in corpus: **1,196**
- Vault: `/Users/ronaldchapman/Library/Mobile Documents/iCloud~md~obsidian/Documents/Supreme Court/Ontology/precedent_vault`

## Execution Plan
1. Baseline audit of ontology coverage and connectivity.
2. Re-scan all SCOTUS cases for citation anchors (syllabus-first, full-opinion fallback).
3. Re-scan all SCOTUS cases for authority anchors (syllabus-first, full-opinion fallback).
4. Re-scan all SCOTUS cases for interpretive edges + hover-card metadata.
5. Rebuild citation index and attempt unresolved-anchor remap.
6. Rebuild ontology metrics/index files.
7. Patch graph builder to increase legal-link density and repair isolated cases.
8. Re-run full connectivity audit and publish before/after metrics.

## Execution Results
### Re-scan runs
- `backfill_scotus_primary_citations.py`
  - scanned: 1,196
  - changed: 0
- `backfill_scotus_citation_anchors.py`
  - scanned: 1,196
  - changed: 0
  - citation anchor instances: 9,411
- `backfill_scotus_authority_anchors.py`
  - scanned: 1,196
  - changed: 0
  - authority anchor instances: 12,218
- `backfill_scotus_interpretive_edges.py --overwrite`
  - scanned: 1,196
  - changed: 0
  - cases with interpretive edges: 1,077
  - interpretive edges present: 5,847
  - missing hover metadata after scan: 0

### Anchor resolution refresh
- `build_scotus_case_citation_index.py`
  - case_count: 1,196
  - unique citation map entries: 191
  - ambiguous citation keys: 53
- `resolve_scotus_unresolved_anchors.py --max-api-queries 0` (local-only remap)
  - unresolved unique citations: 3,413
  - unresolved anchor instances: 7,514
  - anchors updated: 0

### Index/metrics regeneration
- `rebuild_ontology_metrics_and_indices.py`
  - completed successfully

## Graph Repair Patch Applied
### Backend
- File: `/Users/ronaldchapman/Desktop/Acquittify/AcquittifyElectron/main.js`
- Added:
  - authority family classification (`constitution/statute/rule/regulation/guideline`)
  - denser bounded shared-legal-authority edges
  - denser bounded shared-case-citation edges
  - connectivity repair pass (`case_similarity_fallback`) to eliminate isolated cases
- Preserved strongest constitutional linking semantics (`shared_constitution` remains highest-strength case-to-case legal link).

### Frontend
- File: `/Users/ronaldchapman/Desktop/Acquittify/AcquittifyElectron/ui/app.js`
- Added styling for new edge types:
  - `shared_statute`
  - `shared_regulation`
  - `shared_federal_rule`
  - `shared_guideline`
  - `case_similarity_fallback`

## Connectivity Outcome (Post-Patch Estimate)
From full corpus audit:
- Isolated cases before repair: **44**
- Isolated cases after repair: **0**
- Case-to-case edges after repair: **17,106**

## Reports Generated
- `/Users/ronaldchapman/Desktop/Acquittify/reports/scotus_ontology_full_overview_2026-02-19.md`
- `/Users/ronaldchapman/Desktop/Acquittify/reports/scotus_ontology_full_overview_2026-02-19.json`
- `/Users/ronaldchapman/Desktop/Acquittify/reports/scotus_full_rescan_plan_and_execution_2026-02-19.md`
- `/Users/ronaldchapman/Desktop/Acquittify/reports/scotus_interpretive_edge_backfill_2026-02-19_full_rescan.json`
- `/Users/ronaldchapman/Desktop/Acquittify/reports/scotus_unresolved_anchor_resolution_2026-02-19_local_only.json`

## Remaining High-Impact Improvement
- Local SCOTUS citation resolution remains constrained by primary-citation quality in case frontmatter for many modern cases.
- To increase direct case-to-case citation resolution beyond current levels, add a dedicated canonical-citation enrichment pass (opinion header + external metadata merge) and then rerun unresolved-anchor mapping.
