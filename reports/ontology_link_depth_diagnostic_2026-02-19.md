# Ontology Link-Depth Diagnostic (2026-02-19)

## Problem observed
Most cases appeared to have only one visible link in the ontology graph.

## Findings
1. Extraction coverage is present for statute/constitution links.
- SCOTUS cases scanned: 1196
- Authority anchors: 29085
  - statute: 14627
  - constitution: 8141
  - rule: 2747
  - reg: 1004
  - statutes_at_large: 2523
- Interpretive edges: 10051 across 1062 cases
  - STATUTE: 9175
  - CONSTITUTION: 831
  - PRIOR_CASE: 18

2. Direct case-citation density is lower than expected.
- Distinct local case-citation links (from `citation_anchors`): 2451
- Mean case->case links: 2.05
- Median case->case links: 1
- Root cause: local-only citation resolution misses most cited cases because many references are to non-local historic SCOTUS cases.

3. The main UI bottleneck was graph downsampling.
- Default `max_nodes` was 2200.
- Node selection used global degree ranking, which suppressed many source/authority neighbors.
- In fallback mode, graph rendering defaulted to only 180 nodes.

4. Case-law anchor quality remains the limiting factor for dense direct case->case citation links.
- `resolve_scotus_unresolved_anchors.py` (local-only, no external API) found:
  - unresolved unique citations: `6026`
  - unresolved anchor instances: `24532`
  - resolvable via local unique map: `0`
- `build_scotus_case_citation_index.py` found:
  - unique citation count: `191`
  - ambiguous citation count: `53`
- Primary citation quality is mostly docket-style/non-reporter:
  - U.S. reporter-form primary citations: `5 / 1196`
  - non-U.S./docket primary citations: `1191 / 1196`

5. Link-projection logic was suppressing unresolved prior-case citations in the graph.
- Prior behavior dropped case-citation edges unless both source and target were local case nodes.
- Result: many valid citation relationships existed in frontmatter but were invisible in graph depth.

## Changes applied
1. UI graph depth and sampling updates (`AcquittifyElectron/ui/app.js`)
- Increased default `max_nodes` from 2200 to 8000.
- Increased max selectable nodes to 20000.
- Selection now prioritizes case nodes first, then non-case nodes.
- Fallback rendering now uses ontology graph max-node/max-edge budgets (not the hard 180-node fallback cap).

2. Data verification and rescans
- Ran authority anchor rescan: `scripts/backfill_scotus_authority_anchors.py`
  - changed files: 525
- Re-ran interpretive edge backfill: `scripts/backfill_scotus_interpretive_edges.py`
  - no additional changes after rescan (current dataset already synchronized).

3. Case-law link-depth projection updates (`AcquittifyElectron/main.js`)
- Added external cited-case nodes for unresolved/non-local case citations:
  - `case_citation_external`
  - `interpretive_prior_case_external`
- Added bounded case-to-case co-citation edges:
  - `shared_case_citation` (all-pairs up to 12 cases per cited authority; sparse hop links above that threshold).
- Retained local-case guard for canonical local case linkage while no longer discarding unresolved citations.

4. Edge styling updates for new edge types (`AcquittifyElectron/ui/app.js`)
- Added explicit rendering styles for:
  - `shared_case_citation`
  - `case_citation_external`
  - `interpretive_prior_case_external`

5. Resolver patch and rerun (`scripts/resolve_scotus_unresolved_anchors.py`)
- Resolver now uses full local citation alias map in addition to strict unique index.
- Rerun results:
  - files changed: `9`
  - anchors updated: `37`
  - unresolved anchor instances: `24532 -> 24495`

6. Syllabus-first anchor policy + sparse-syllabus fallback applied end-to-end.
- Citation anchors are now extracted from syllabus first, with full-opinion fallback when:
  - no syllabus exists, or
  - syllabus evidence is too sparse to determine anchors.
- Authority anchors follow the same rule.
- Interpretive edge backfill now uses syllabus-first authority extraction with the same sparse-syllabus fallback.

7. Post-rollout depth metrics (after syllabus-first + fallback + interpretive overwrite).
- Citation anchors:
  - total: `9411`
  - locally resolved: `1897`
  - unresolved: `7514`
- Interpretive edges:
  - total: `5847`
  - prior-case interpretive edges: `295`
- Simulated ontology graph case-link structure from current vault:
  - `case_citation`: `1685`
  - `interpretive_prior_case`: `295`
  - `shared_case_citation`: `8719`
  - `case_citation_external`: `6491`
  - local case-to-case edges total: `10699`
  - mean local case degree: `17.89` (median `15`, p90 `34`)

## Expected post-fix depth impact
- Simulated with current SCOTUS dataset and updated projection logic:
  - external cited-case nodes: `6019`
  - citation-derived edges (direct + external): `28088`
  - additional co-citation case-to-case edges: `22732`
  - local case-case degree (citation-only projection):
    - mean: `42.14`
    - median: `35`
    - p90: `89`

## Residual known gap
- 134 cases still have no interpretive edges.
- Primary cause: missing authority anchors in those notes (116 files), plus sparse citation anchors (54 files).
- This is source-content quality/coverage, not graph rendering logic.

## Validation
- `node --check AcquittifyElectron/main.js` passed
- `node --check AcquittifyElectron/ui/app.js` passed
- `python3 -m py_compile scripts/resolve_scotus_unresolved_anchors.py` passed
