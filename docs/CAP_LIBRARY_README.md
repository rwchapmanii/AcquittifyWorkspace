# Acquittify CAP Library Plan + Features

This document describes the plan to build a CAP case‑law library inside Acquittify that uses existing
embeddings, CAP metadata, and local PDFs.

Related locations reference: `docs/CAP_LIBRARY_LOCATIONS.md`.

## Why a mapping tool is needed
- CAP metadata currently points to **CAP JSON case files** (`.../cases/*.json`), while the **PDFs live separately**
  (`.../case-pdfs/*.pdf`).
- To show a PDF in the library, we need a reliable mapping from the CAP metadata record to the
  correct PDF path.
- The mapping can be deterministic for most cases (replace `/cases/` → `/case-pdfs/` and `.json` → `.pdf`),
  but should also validate existence and fall back to `download_manifest.jsonl` when needed.

## Plan (updated)
### Phase 0 — Inventory & Validation
- Confirm Chroma collection + metadata shape (CAP fields).
- Confirm raw PDF location and structure.
- Validate that `doc_id = cap_{cap_id}` exists in both embeddings and metadata.

### Phase 1 — Case ↔ PDF Mapping Tool (required)
- Build a small mapping utility:
  - Input: CAP metadata `download_url` / `path` (JSON path), `reporter_slug`, `page`, `cap_id`.
  - Output: local PDF path (or null with reason).
  - Strategy:
    1) Deterministic transform (`/cases/` → `/case-pdfs/`, `.json` → `.pdf`) and check file exists.
    2) If not found, look up in `acquittify-data/logs/download_manifest.jsonl` for a matching file name.
    3) Cache resolved paths in a small index (SQLite or JSONL).
  - Implemented by `scripts/cap_pdf_map.py` and cached to `reports/cap_pdf_index.jsonl`.

### Phase 2 — Canonical Case Index
- Create a lightweight case index (SQLite or Postgres table):
  - `case_id`, `doc_id`, `cap_id`, `case_name`, `court`, `decision_date`,
    `citations`, `document_citation`, `reporter_slug`, `pdf_path`, `source`.
- Populate from Chroma metadata + mapping tool.
  - Implemented as JSONL index at `reports/cap_case_index.jsonl` via `scripts/cap_case_index.py`.

### Phase 3 — Retrieval + Search API
- Add API endpoints:
  - `GET /library/search?q=...`
  - `GET /library/case/{case_id}`
  - `GET /library/case/{case_id}/pdf` (serves the PDF)
- Search uses Chroma embeddings and groups by `case_id`.
  - Implemented in `acquittify/library_api.py` (run with `scripts/run_library_api.sh`).

### Phase 4 — Library UI
- Add a “Caselaw Library” page in Acquittify:
  - Search + filters (court/year)
  - Result cards with citation, short summary, and “View PDF”
  - Case detail view with metadata + key passages

### Phase 5 — Summaries & Caching (heuristic)
- Create short structured summaries from metadata + representative text (heuristics, not LLM).
- Cache summaries in the case index.
- Incremental refresh when new CAP ingest runs (rebuilds heuristic summaries).

## Library features (target)
- Vector search across CAP embeddings.
- Structured case metadata and clean citations.
- Stable PDF links (local viewer).
- Grouped results by case, not by chunk.
- Optional filters (court, year, authority tier).
- Related cases based on shared jurisdiction + taxonomy overlap.
- Related cases now also factor shared citations and similar authority tiers.

## Success criteria
- Any search result includes:
  - case title
  - proper citation
  - working PDF link
  - summary snippet
