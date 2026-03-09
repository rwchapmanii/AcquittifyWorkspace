# Ontology Graph Case UX Upgrade
Date: 2026-02-18

## Plan
1. Normalize graph case labels to `Case Name (Year)`.
2. Enrich ontology case nodes with citation/summary/essential-holding/PDF path metadata.
3. Add case hover card in ontology graph with citation, essential holding, summary.
4. Add right-side case PDF reader panel and wire case click + hover-card actions.
5. Recompile SCOTUS ontology and rebuild metrics/indexes to populate metadata.

## Execution Summary
- Implemented label logic in ontology graph rendering for case nodes.
- Added hover card with:
  - citation
  - essential holding
  - case summary
  - `Open PDF` and `Open Note` actions
- Added right sidebar case reader with embedded PDF iframe.
- Clicking a case node now opens the case reader sidebar.
- Propagated `opinion_pdf_path` through compile pipeline and SCOTUS CSV runner.

## Data Refresh
- SCOTUS recompile completed:
  - attempted: 1191
  - succeeded: 1191
  - failed: 0
  - changed_total: 1197
- Metrics/index rebuild completed (15 files changed).
- Case notes with `opinion_pdf_path`: 1151

## Validation
- Python tests: `45 passed` (`tests/ontology`).
- JS syntax checks passed:
  - `AcquittifyElectron/main.js`
  - `AcquittifyElectron/ui/app.js`
