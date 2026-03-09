# Local/Desktop Data Control Roadmap (Archived)

## Status

As of **2026-03-09**, the Electron desktop runtime and Streamlit ingestion surfaces were retired from this repository.

This document is retained as a historical record of prior local-desktop planning and is **not** an active implementation roadmap.

## Current canonical approach

Data control and tenant isolation now live in the AWS-hosted/server-side stack:
- API and web runtime: `trial-discovery-ai/backend/`, `trial-discovery-ai/frontend/`
- Ingestion services: `document_ingestion_backend.py`, `ingestion_agent/`, `ingestion_infra/`, `scripts/nightly_caselaw_ingest.py`
- Governance and operational controls: `admin_ui/`, `migrations/`, `docs/caselaw_nightly_ingest.md`

## Historical scope (for reference only)

The archived desktop roadmap focused on:
- local workspace boundaries
- per-workspace retrieval isolation
- offline/egress controls
- export/delete/restore lifecycle workflows
- desktop packaging and release hardening

Those objectives are now addressed through server-side tenancy, guarded ingestion pipelines, and AWS-managed deployment controls.
