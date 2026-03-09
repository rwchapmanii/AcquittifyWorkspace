# Ontology Link-Density Diagnosis and Fix (2026-02-19)

## User-visible symptom
Most ontology graph nodes appeared to have only one connection.

## Root causes
1. External citation nodes were modeled as regular `case` nodes.
- Unresolved citations generated many external case nodes.
- Citation anchor audit (current corpus):
  - unresolved citation anchor instances: 7514
  - unresolved unique citations: 3413
- External citation nodes are often low-degree and made the graph look sparse.

2. Shared-authority case-to-case links were computed before interpretive authority edges were indexed.
- This reduced shared statute/constitutional clustering impact from interpretive extraction.

## Fixes applied
1. External node typing separation
- File: `AcquittifyElectron/main.js`
- Change: `ensureExternalCaseNode()` now sets `nodeType: external_case` (instead of `case`).
- Effect: default ontology graph no longer treats unresolved external citations as local case nodes.

2. Shared-authority pass order corrected
- File: `AcquittifyElectron/main.js`
- Change: `processInterpretiveEdges()` now runs before `processCaseAuthorityEdges()`.
- Effect: interpretive authority anchors contribute to shared statute/rule/constitution case-to-case linkage.

3. UI filtering support for external-case nodes
- File: `AcquittifyElectron/ui/app.js`
- Added node color for `external_case`.
- Added node-type checkbox `External Case` (off by default).
- `isCaseOntologyNode()` now excludes `external_case` from local case hover-card behavior.

## Validation run
- `node --check AcquittifyElectron/main.js` passed
- `node --check AcquittifyElectron/ui/app.js` passed

SCOTUS full data refresh run after patch:
- `backfill_scotus_primary_citations.py`: scanned 1196, changed 0
- `build_scotus_case_citation_index.py`: case_count 1196, unique_citation_count 191
- `backfill_scotus_citation_anchors.py`: scanned 1196, changed 0, total citation anchors 9411
- `backfill_scotus_authority_anchors.py`: scanned 1196, changed 0, total authority anchors 12218
- `backfill_scotus_interpretive_edges.py --overwrite`: scanned 1196, changed 0, interpretive edges 5847
- `resolve_scotus_unresolved_anchors.py --max-api-queries 0`: unresolved unique 3413, unresolved instances 7514, updates 0
- `rebuild_ontology_metrics_and_indices.py`: changed files 13

## Remaining data quality limitation
Primary citation canonicalization is still weak (`191` unique citation keys for `1196` SCOTUS cases), which limits local case-citation resolution and causes many unresolved external citations.
