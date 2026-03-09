# Anchor Resolution Steps 1-4 Execution (2026-02-18)

## Step 1: Canonical SCOTUS Citation Index
Command:
- `scripts/build_scotus_case_citation_index.py`

Output:
- `/Users/ronaldchapman/Library/Mobile Documents/iCloud~md~obsidian/Documents/Supreme Court/Ontology/precedent_vault/indices/scotus_case_citation_index.json`

Result:
- `case_count`: 1196
- `unique_citation_count`: 191
- `ambiguous_citation_count`: 53

## Step 2: Integrate Index into Local Resolution
Code updates:
- `/Users/ronaldchapman/Desktop/Acquittify/acquittify/ontology/vault_writer.py`
  - `load_existing_case_citation_map()` now merges `indices/scotus_case_citation_index.json` `unique_map`.
- `/Users/ronaldchapman/Desktop/Acquittify/scripts/compile_precedent_ontology.py`
  - Added canonical-citation remap: resolver output -> local case IDs using local citation map/index.

## Step 3: Backfill Docket-Only Primary Citations
Command:
- `scripts/backfill_scotus_primary_citations.py`

Output report:
- `/Users/ronaldchapman/Desktop/Acquittify/reports/scotus_primary_citation_backfill_2026-02-18.json`

Result:
- `scanned_files`: 1196
- `changed_files`: 0 (already backfilled in current vault state)

## Step 4: Resolve Remaining Unresolved Anchors (Local + External)
Command:
- `scripts/resolve_scotus_unresolved_anchors.py --max-api-queries 50`
- Runtime env: `ACQ_ONTOLOGY_REQUEST_TIMEOUT=5`

Output report:
- `/Users/ronaldchapman/Desktop/Acquittify/reports/scotus_unresolved_anchor_resolution_2026-02-18.json`

Result:
- `unresolved_unique_before`: 6053
- `unresolved_anchor_instances_before`: 24593
- `local_index_unique_resolved`: 27
- `api_queries`: 50
- `api_any_resolution_count`: 0
- `api_local_remap_count`: 0
- `files_changed`: 11
- `anchors_updated`: 61
- `unresolved_anchor_instances_after`: 24532

## Net Effect on Anchor Resolution Rate
Current vault totals:
- `anchors_total`: 28088
- `anchors_resolved`: 3556
- `anchor_resolution_rate`: 12.66%
