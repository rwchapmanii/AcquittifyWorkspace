# SCOTUS Sweep + Re-resolve + Rebuild (2026-02-19)

## Commands executed
1. `backfill_scotus_primary_citations.py` (sweep)
2. `build_scotus_case_citation_index.py`
3. `resolve_scotus_unresolved_anchors.py` (local re-resolve)
4. `rebuild_ontology_metrics_and_indices.py`

## Results
- Sweep (`backfill_scotus_primary_citations.py`)
  - scanned: `1196`
  - changed: `0`
  - report: `/Users/ronaldchapman/Desktop/Acquittify/reports/scotus_primary_citation_backfill_2026-02-19_sweep_rerun.json`

- Citation index rebuild
  - case_count: `1196`
  - unique_citation_count: `191`
  - ambiguous_citation_count: `53`

- Anchor re-resolution (`--max-api-queries 0` local-only)
  - unresolved_unique_before: `3413`
  - unresolved_instances_before: `7514`
  - local_index_unique_resolved: `0`
  - files_changed: `0`
  - anchors_updated: `0`
  - unresolved_instances_after: `7514`
  - report: `/Users/ronaldchapman/Desktop/Acquittify/reports/scotus_unresolved_anchor_resolution_2026-02-19_rerun_local.json`

- Metrics/index rebuild
  - holdings_loaded: `9`
  - issues_loaded: `4`
  - relations_loaded: `0`
  - changed_files: `13`

## Blocking issue identified
CourtListener citation lookup requires authentication.
- Unauthenticated test to `https://www.courtlistener.com/api/rest/v4/citation-lookup/` returned `401`.
- In this environment, `COURTLISTENER_API_TOKEN` and `ACQ_COURTLISTENER_API_TOKEN` are unset.

Without a token, external unresolved anchor remapping cannot proceed beyond local index matching.
