# Acquittify

Acquittify is an AWS-hosted legal intelligence platform for federal case analysis, ingestion, and taxonomy-driven retrieval.

Primary goal:
- Ingest litigation documents and caselaw into governed storage and vector/search pipelines.
- Serve agent-assisted retrieval and ontology-aware analysis through web/API surfaces.

## Canonical Runtime (AWS-First)

The canonical product runtime is server-hosted:
- Web/API application: `trial-discovery-ai/backend/` and `trial-discovery-ai/frontend/`
- Ingestion services: `ingestion_agent/`, `ingestion_infra/`, `document_ingestion_backend.py`
- Operations/admin service: `admin_ui/`

There is no desktop runtime in this repository.

## Repository Layout (Core)

- `trial-discovery-ai/` AWS web app (backend API, frontend UI, deploy assets).
- `acquittify/` Shared Python retrieval/ingestion/ontology package.
- `ingestion_agent/` Document parsing/chunking and ingest orchestration.
- `ingestion_infra/` CourtListener bulk/API ingestion infrastructure.
- `scripts/` Batch jobs, nightly ingest, validation, and maintenance tooling.
- `admin_ui/` Admin and governance interfaces.
- `tests/` Python test suite.
- `docs/` Architecture and operations references.
  - Nightly CourtListener ingest guide: `docs/caselaw_nightly_ingest.md`

## QA Checks

Python checks:

```bash
cd /Users/ronaldchapman/Desktop/AcquittifyWorkspace
pytest -q
```

Service-specific runtime checks:
- See `trial-discovery-ai/README.md` for web/API runtime details.
- See `docs/caselaw_nightly_ingest.md` and `README_ACQUITTIFY_INGEST.md` for ingestion operations.

## External Data Policy

Large mutable data must stay out of Git:
- `acquittify-data/`
- `Corpus/`
- `Obsidian/`
- `Acquittify Storage/`
- `Casefiles/`
- `data/transcripts/`

Setup guide:
- `docs/EXTERNAL_DATA_SETUP.md`

## Selected Environment Variables

- `ACQUITTIFY_DATA_ROOT` external data root (recommended: outside repo)
- `ACQUITTIFY_DATASET_DIR` CAP/raw dataset directory override
- `ACQUITTIFY_ONTOLOGY_VAULT` ontology vault path override
- `ACQUITTIFY_OPENAI_API_KEY` API key for API/ingestion services
- `ACQUITTIFY_AGENT_MODEL` model selection for retrieval/analysis services
- `PEREGRINE_API_URL` Peregrine API base URL
- `PEREGRINE_API_TOKEN` optional Peregrine API token
