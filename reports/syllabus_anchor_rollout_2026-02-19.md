# Syllabus-First Anchor Rollout (2026-02-19)

## Policy implemented
- Anchor extraction now uses:
  1. Syllabus region at the beginning of the opinion (`Syllabus` header -> opinion-body marker).
  2. Full-opinion fallback if syllabus is missing.
  3. Full-opinion fallback if syllabus does not produce usable anchors.

## Code changes
- Added shared syllabus scope module:
  - `acquittify/ontology/anchor_scope.py`
- Updated compiler to use syllabus-first extraction and to persist scope metadata:
  - `scripts/compile_precedent_ontology.py`
  - writes `sources.anchor_citation_scope`
  - writes `sources.anchor_authority_scope`
  - writes `sources.anchor_syllabus_span` when available
- Updated authority backfill to syllabus-first behavior:
  - `scripts/backfill_scotus_authority_anchors.py`
- Added citation anchor backfill script with syllabus-first behavior:
  - `scripts/backfill_scotus_citation_anchors.py`

## Applied to SCOTUS vault
Vault: `/Users/ronaldchapman/Library/Mobile Documents/iCloud~md~obsidian/Documents/Supreme Court/Ontology/precedent_vault`

### Citation anchor backfill
- Scanned: `1196`
- Changed: `1196`
- Total citation anchors: `5752`
- Scope counts:
  - `syllabus`: `775`
  - `full_opinion_no_syllabus`: `420`
  - `full_opinion_fallback_empty_syllabus`: `1`

### Authority anchor backfill
- Scanned: `1196`
- Changed: `1196`
- Total authority anchors: `6209`
- Scope counts:
  - `syllabus`: `693`
  - `full_opinion_no_syllabus`: `420`
  - `full_opinion_fallback_empty_syllabus`: `83`

### Post-backfill summary
- Cases with citation anchors: `1109`
- Cases with authority anchors: `1079`
- Citation anchors resolved to local case IDs: `1576`

## Maintenance
- Regenerated ontology metrics/index files:
  - `scripts/rebuild_ontology_metrics_and_indices.py`
