# Ontology Graph Diagnostics Report (2026-02-19)

## Scope
- Investigated why Caselaw Ontology graph did not reflect new interpretive edges.
- Investigated why many hover cards appeared to have missing data.

## Root causes found
1. `interpretive_edges` were not present in SCOTUS case notes.
- Pre-fix count: `0 / 1196` case files with `interpretive_edges`.
- Cause: SCOTUS vault had not been reprocessed for the new interpretive-edge payload.

2. Hover data gaps were concentrated in metadata holes.
- Before backfill: `8` cases missing summary/essential-holding core fields.
- Frontmatter key variance also required UI fallback handling (`primary_citation`, `opinion_url`, `opinion_pdf_path` at multiple levels).

## Fixes applied
1. Full SCOTUS interpretive-edge + hover metadata backfill.
- Script: `scripts/backfill_scotus_interpretive_edges.py`
- Run report: `reports/scotus_interpretive_edge_backfill_2026-02-19.json`
- Cleanup reruns:
  - `reports/scotus_interpretive_edge_backfill_2026-02-19_rerun.json`
  - `reports/scotus_interpretive_edge_backfill_2026-02-19_cleanup.json`

2. Graph loader hardening in Electron.
- File: `AcquittifyElectron/main.js`
- Changes:
  - Added fallback support for top-level citation/pdf metadata keys.
  - Added local-case guard to suppress unknown external case placeholders in citation/prior-case edge wiring.

3. Metrics/index regeneration.
- Script: `scripts/rebuild_ontology_metrics_and_indices.py`
- Vault: `/Users/ronaldchapman/Library/Mobile Documents/iCloud~md~obsidian/Documents/Supreme Court/Ontology/precedent_vault`

## Post-fix state
- Total SCOTUS cases scanned: `1196`
- Cases with `interpretive_edges`: `1062`
- Total interpretive edges written: `10051`
- Hover core missing (title/citation/summary/holding): `0`
- Cases still without interpretive edges: `134`
  - Primary reason: no authority anchors in those notes (`116`)

## Validation
- `node --check AcquittifyElectron/main.js` passed
- `node --check AcquittifyElectron/ui/app.js` passed
- `python3 -m py_compile scripts/backfill_scotus_interpretive_edges.py` passed
