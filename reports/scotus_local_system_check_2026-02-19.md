# SCOTUS Ontology Local-Only System Check (2026-02-19)

## Scope
- Source corpus: local Supreme Court vault only.
- No CourtListener/API resolution used in this run.
- Ontology root: `/Users/ronaldchapman/Library/Mobile Documents/iCloud~md~obsidian/Documents/Supreme Court/Ontology/precedent_vault`

## Executed Pipeline
1. Full local SCOTUS recompile from local CSV (resolver disabled, extractor disabled)
2. Dedupe pass on SCOTUS case notes
3. Citation-anchor backfill (syllabus-first with full-opinion fallback)
4. Authority-anchor backfill
5. Interpretive edge backfill (`--overwrite`)
6. Citation index rebuild
7. Local-only unresolved-anchor pass (`--max-api-queries 0`)
8. Metrics/index rebuild
9. Graph-link health diagnostic from local frontmatter

## Key Results
- Recompile: `attempted=1191`, `succeeded=1191`, `failed=0`
- Dedupe removed `1076` duplicate SCOTUS case notes
- Citation index now: `case_count=1194`, `unique_citation_count=173`, `ambiguous_citation_count=49`
- Citation anchors: `total=9431`, `cases_with_citation_anchors=1131/1194`
- Authority anchors: `total=12216`, with
  - `constitution=3244`
  - `statute=6522`
  - `rule=822`
  - `reg=450`
- Interpretive edges: `5833` total across `1076` cases

## Connectivity Diagnostic (Projected Case-Case)
- Direct case-citation edges: `1613`
- Interpretive prior-case edges: `282`
- Shared authority edges: `5184`
- Shared constitutional edges: `4061`
- Union case-case edges: `10542`
- Linked cases: `1137/1194` (`95.23%`)
- Average degree: `17.66` (median `15`)

## Remaining Constraint
- Local unresolved citation anchors remain high (`7602` instances; resolution ratio `19.39%`) because many citations point outside the in-vault SCOTUS subset or use unresolved placeholders.

## Artifacts
- `/Users/ronaldchapman/Desktop/Acquittify/reports/scotus_local_only_recompile_full_2026-02-19.json`
- `/Users/ronaldchapman/Desktop/Acquittify/reports/scotus_dedupe_dryrun_2026-02-19.json`
- `/Users/ronaldchapman/Desktop/Acquittify/reports/scotus_dedupe_apply_2026-02-19.json`
- `/Users/ronaldchapman/Desktop/Acquittify/reports/scotus_citation_anchor_backfill_2026-02-19.json`
- `/Users/ronaldchapman/Desktop/Acquittify/reports/scotus_authority_anchor_backfill_2026-02-19.json`
- `/Users/ronaldchapman/Desktop/Acquittify/reports/scotus_interpretive_edges_rebuild_2026-02-19.json`
- `/Users/ronaldchapman/Desktop/Acquittify/reports/scotus_graph_health_2026-02-19.json`
