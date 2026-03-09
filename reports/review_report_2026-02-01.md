# Acquittify Review Report — 2026-02-01

## Scope
- Codebase scan for deprecated/unused code paths, TODOs, and obvious runtime issues.
- Minimal improvement applied with sanity check.
- Ran available tests and sanity scripts.

## Changes Applied
- Fixed module import path handling for the taxonomy coverage sanity script to work regardless of current working directory.
  - File: scripts/taxonomy_coverage_sanity.py

### Suggested PR message (includes “what changed” note)
- **what changed:** Ensure taxonomy coverage sanity script adds project root to `sys.path` for reliable imports.

## Tests & Sanity Checks
- `pytest -q` → **failed**: missing `fitz` (PyMuPDF) module during collection.
- `scripts/ui_sanity_check.py` → **passed**.
- `scripts/taxonomy_coverage_sanity.py` → **passed** after fix.

## Findings (No code changes yet)
- Deprecated entrypoints are present and still callable:
  - `acquittify_ingest.py` (deprecated warning)
  - `ingestion_agent/main.py` (deprecated warning)
- Ingestion infra runner still has TODOs for downstream parsing/chunking triggers.
- Several scripts rely on being run from repo root; the taxonomy sanity script now handles this explicitly.
- Electron launcher logs are now captured and surfaced via a diagnostic page (previous work).

## Issues Blocking Full Test Run
- PyMuPDF is listed in requirements but not available in the current venv, causing `tests/test_transcript_parser.py` to fail on import `fitz`.
  - Recommended action: reinstall dependencies or recreate `.venv` to ensure `PyMuPDF` is installed.

## Recommendations
1. **Dependency verification**: Recreate `.venv` or run a dependency sync so `PyMuPDF` is installed, then re-run tests.
2. **Script resilience**: Consider adding the same project-root insertion to other scripts that import top-level modules (optional, low risk).
3. **Deprecated entrypoints**: Keep for backward compatibility, but consider documenting removal timeline.

## Next Steps I Can Take
- Run a dependency sync and re-run tests once approved.
- Apply the same import-path fix to other scripts that run from `scripts/` if desired.
- Draft a cleanup plan for deprecated entrypoints with a migration notice.
