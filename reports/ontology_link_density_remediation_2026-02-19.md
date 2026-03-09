# Ontology Link-Density Remediation (2026-02-19)

## Problem
Graph still appeared under-linked (many cases with ~1 visible connection).

## Root causes confirmed
1. Authority anchors were too granular at subsection level (e.g., `28 U.S.C. § 2254(d)(1)` vs `§ 2254(d)(2)`), reducing overlap-based linking.
2. Sparse-link strategy for high-frequency authorities used adjacent ordering only, causing repeated same-neighbor pairs and weak visible clustering.
3. Node selection favored case nodes too heavily under node limits, suppressing source/issue context nodes that expose statutory/constitutional hubs.

## Code changes applied
- `AcquittifyElectron/main.js`
  - Added authority shared-key normalization for link generation:
    - `deriveAuthoritySharedKeys(...)`
    - Collapses subsection-level IDs to section-core IDs for statutes, regulations, federal rules, and guidelines.
  - Added unified registration pipeline:
    - `registerAuthorityForCase(...)`
    - Ensures derived keys feed shared-authority case-case linking.
  - Upgraded high-frequency shared-link generation:
    - deterministic rotation + long-hop sparse links (`addSparseAuthorityPairs(...)`)
    - denser constitutional linkage while still bounded.
  - Ensured interpretive authority data is included before shared-authority graph construction.

- `AcquittifyElectron/ui/app.js`
  - Updated ontology node selection strategy to reserve non-case capacity (source/issue/holding) so hubs remain visible even with high case counts.
  - Prioritizes non-case nodes by ontology relevance (`source`, `issue`, `holding`, ...).

## Validation
- JS syntax checks passed:
  - `node --check AcquittifyElectron/main.js`
  - `node --check AcquittifyElectron/ui/app.js`

## Expected impact (authority-link projection audit)
Using current SCOTUS corpus authority anchors:
- Prior projection:
  - edges: `5369`
  - mean degree: `8.98`
  - median degree: `6`
  - isolates: `201`
  - degree <= 1: `284`
- Post-remediation projection:
  - edges: `9107`
  - mean degree: `15.23`
  - median degree: `13`
  - isolates: `155`
  - degree <= 1: `200`

This increases link depth and strengthens clustering around shared authorities.

## Additional hardening
- Connectivity backfill is now applied to underlinked cases (target minimum case-degree = 3), not only fully isolated cases.
- Edge type used: `case_similarity_fallback` with deterministic feature scoring.

Projection check after this hardening (authority + fallback model):
- cases: `1196`
- edges: `9704`
- mean degree: `16.23`
- median degree: `13`
- p90 degree: `33`
- isolated cases: `0`
- degree <= 1: `0`
