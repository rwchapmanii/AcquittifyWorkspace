# Ontology Graph Link-Depth Patch (2026-02-19)

## Problem observed
Syllabus-first backfill succeeded, but graph depth remained shallow because non-constitutional shared-authority case-to-case edges were aggressively dropped.

## Code changes
- `AcquittifyElectron/main.js`
  - Added authority family classification (`constitution/statute/regulation/rule/guideline/authority`).
  - Added bounded shared edge generation for high-frequency non-constitutional authorities instead of skipping them.
  - Added edge types:
    - `shared_statute`
    - `shared_regulation`
    - `shared_federal_rule`
    - `shared_guideline`
  - Expanded `shared_case_citation` density:
    - dense threshold `12 -> 18`
    - sparse link hop `2 -> 3` for medium clusters.
  - Included interpretive authority targets in shared-authority indexing.
- `AcquittifyElectron/ui/app.js`
  - Added visual styling (color/width) for new edge types.

## Validation
- JS syntax checks passed:
  - `node --check AcquittifyElectron/main.js`
  - `node --check AcquittifyElectron/ui/app.js`

## Data/impact estimates on current SCOTUS vault
- Syllabus-first scope in notes remains active:
  - citation scope: `syllabus=581`, `full_opinion_no_syllabus=420`, `full_opinion_fallback_sparse_syllabus=195`
  - authority scope: `syllabus=400`, `full_opinion_no_syllabus=420`, `full_opinion_fallback_sparse_syllabus=376`
- Estimated pairwise case-link gain from new non-constitutional authority sharing logic:
  - old non-constitutional shared authority pairs: `2171`
  - new non-constitutional shared authority pairs: `3214`
  - delta: `+1043`
- Estimated pairwise case-link gain from shared case citation tuning:
  - old: `8719`
  - new: `9624`
  - delta: `+905`

Expected net effect: significantly denser case-to-case topology in ontology graph.
