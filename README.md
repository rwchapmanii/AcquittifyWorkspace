# Acquittify

Acquittify is an Electron desktop application for federal case intelligence.

Primary goal:
- Visualize federal cases and discovery against Acquittify taxonomy.
- Use agent-assisted retrieval to connect facts, precedent, and evidence faster in active litigation.

## Canonical Runtime

Acquittify now runs through Electron only:
- Entry point: `AcquittifyElectron/main.js`
- Renderer: `AcquittifyElectron/ui/index.html`, `AcquittifyElectron/ui/app.js`, `AcquittifyElectron/ui/styles.css`
- Bridge: `AcquittifyElectron/preload.js`
- Launcher: `launch_acquittify.sh`

## Repository Layout (Core)

- `AcquittifyElectron/` Desktop runtime and IPC handlers.
- `acquittify/` Shared Python logic (retrieval/ingestion helpers and ontology utilities).
- `scripts/` Operational scripts for ingestion/evaluation/maintenance.
- `tests/` Python test suite.
- `docs/` Architecture and data setup references.
  - Nightly CourtListener caselaw ingest guide: `docs/caselaw_nightly_ingest.md`

## Local Run

```bash
cd AcquittifyElectron
npm install
npm run start
```

or from repo root:

```bash
bash launch_acquittify.sh
```

## QA Checks

Desktop checks:

```bash
cd AcquittifyElectron
npm run check:syntax
npm run check:pdf-layout
npm run check:ui-smoke
```

Python checks:

```bash
cd /Users/ronaldchapman/Desktop/Acquittify
pytest -q
```

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
- `ACQUITTIFY_OPENAI_API_KEY` API key for desktop agent calls
- `ACQUITTIFY_AGENT_MODEL` model for desktop agent calls
- `PEREGRINE_API_URL` Peregrine API base URL
- `PEREGRINE_API_TOKEN` optional Peregrine API token
