# CAP Library Locations (Embeddings + Metadata + PDFs)

This README documents where the CAP embeddings, CAP metadata, case IDs, and raw PDFs live in this repo.

## Embeddings backend (CAP metadata lives here)
- **Backend:** ChromaDB persistent storage.
- **Default location:** `Corpus/Chroma`
  - Used by CAP ingest: `scripts/ingest_cap_jsonl.py` (creates `chromadb.PersistentClient(path=str(chroma_dir))`, default `Corpus/Chroma`).
  - Collection name & embedding model: `acquittify/config.py` (`CHROMA_COLLECTION = "acquittify_corpus"`, `EMBEDDING_MODEL_ID = "all-MiniLM-L6-v2"`).
- **Where CAP metadata is stored:** as Chroma **metadata** alongside each embedding chunk.
  - Ingest writes metadata per chunk: `scripts/ingest_cap_jsonl.py` (`metadatas.append(clean_meta)` → `upsert_or_add(..., metadatas=metadatas)`).
  - Sample metadata payloads with CAP fields are logged in `reports/cap_ingest_inspect_sample.jsonl` and `reports/ingest_CAP_log.jsonl`.

## Case IDs (CAP metadata + embeddings)
- **doc_id format:** `cap_{cap_id}`
  - Defined in `scripts/ingest_cap_jsonl.py` (`_doc_id()` uses `cap_id` when present).
- **Stored fields in metadata:**
  - `doc_id` and `cap_id` are included in the CAP metadata for every chunk.
  - Example entries in `reports/cap_ingest_inspect_sample.jsonl` show `doc_id` + `cap_id` in the `metadata` object.

## Raw CAP documents (PDFs)
- **PDF storage location:** `acquittify-data/raw/static.case.law/**/case-pdfs/*.pdf`
  - Example files exist under paths like:
    - `acquittify-data/raw/static.case.law/us/104/case-pdfs/0769-01.pdf`
  - Download logs confirm local PDF paths:
    - `acquittify-data/logs/download_manifest.jsonl`
    - `acquittify-data/logs/download_checkpoints.jsonl`

## Raw CAP JSON (source text)
- The ingest metadata currently points to CAP JSON case files (not PDFs) via `download_url` / `path`, e.g.:
  - `acquittify-data/raw/static.case.law/us/1/cases/0001-01.json`
  - See `reports/ingest_CAP_log.jsonl` and `reports/cap_ingest_inspect_sample.jsonl`.

## Summary
- **Embeddings + CAP metadata live together in Chroma** (`Corpus/Chroma`, collection `acquittify_corpus`).
- **Case IDs are stable** via `doc_id = cap_{cap_id}` stored in metadata for each embedding.
- **Raw PDFs are already present** under `acquittify-data/raw/static.case.law/**/case-pdfs/*.pdf`.
- **Raw JSON case files** are referenced in CAP metadata (`download_url`/`path`).

## Cached PDF mapping index
- **Index file (generated):** `reports/cap_pdf_index.jsonl`
- **Generator script:** `scripts/cap_pdf_map.py`
  - Resolves `download_url` / `path` in CAP metadata to a local PDF path.
  - Uses a deterministic transform + `acquittify-data/logs/download_manifest.jsonl` fallback.

## Canonical CAP case index (library)
- **Index file (generated):** `reports/cap_case_index.jsonl`
- **Generator script:** `scripts/cap_case_index.py`
  - Aggregates CAP metadata at the case level.
  - Attaches PDF path from `cap_pdf_index.jsonl`.
  - Stores cached summaries for library display.

## Heuristic summaries
- **Generator:** `scripts/cap_case_index.py` (summary mode `heuristic`)
- **Cache location:** `reports/cap_case_index.jsonl` (`summary`, `summary_method`, `summary_updated_at`)
