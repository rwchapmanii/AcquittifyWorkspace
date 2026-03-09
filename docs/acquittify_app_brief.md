# Acquittify Workspace – Technical + Pricing Brief

_Last updated: 2026-03-09_

## 1. Purpose and Positioning
- **Mission:** Help federal criminal-defense teams map every fact, filing, witness, and precedent to Acquittify’s criminal-procedure taxonomy so they can spot leverage faster.
- **Primary surfaces:**
  - **AWS-hosted web product** (`trial-discovery-ai/backend`, `trial-discovery-ai/frontend`) for day-to-day case work, discovery review, search, and ontology views.
  - **Server-side ingestion services** (`document_ingestion_backend.py`, `ingestion_agent/`, `ingestion_infra/`, `scripts/nightly_caselaw_ingest.py`) for PDF/transcript/caselaw intake, normalization, and indexing.
  - **Ops/governance interfaces** (`admin_ui/`, migrations, and ingestion guardrail scripts) for tenant controls, taxonomy lifecycle operations, and health monitoring.
- **Operating principle:** Keep mutable case data out of Git and inside external roots defined by `ACQUITTIFY_DATA_ROOT`, while code + ontology live in this repo.

## 2. High-Level Architecture
| Layer | Components | Notes |
| --- | --- | --- |
| **Web/API runtime** | `trial-discovery-ai/backend/app/*`, `trial-discovery-ai/frontend/src/*` | Backend exposes authenticated APIs for matters, uploads, search, ontology, and agent workflows; frontend consumes those APIs as the primary user experience. |
| **Python shared logic** | `acquittify/` package | Chunking (`chunking.py`), embeddings (`config.py`), taxonomy helpers (`ontology/`), Chroma utilities, case workspace helpers (`local_workspace.py`), and ingestion pipelines (`acquittify/ingest/*`). |
| **Ops + ingestion agents** | `document_ingestion_backend.py`, `taxonomy_embedding_agent.py`, `ingestion_agent/`, `ingestion_infra/`, `scripts/nightly_caselaw_ingest.py` | Handle PDF/transcript text extraction, metadata synthesis via Ollama/Qwen models, duplicate detection, CourtListener/CAP ingest, and writes into Chroma + derived Postgres tables. |
| **Data stores** | Postgres (schemas below), ChromaDB (vector store), AWS S3 (external storage tiers) | Local ingestion writes to `<workspace>/documents`, `<workspace>/processed`, `<workspace>/chroma`; cloud copies synced to S3 buckets described in `docs/EXTERNAL_DATA_SETUP.md`. |
| **External services** | OpenAI (default), OpenClaw Gateway, CourtListener, CAP, Peregrine | API/worker services call model and data providers through controlled server-side integrations. CourtListener + CAP feeds flow through nightly ingestion scripts (`docs/caselaw_nightly_ingest.md`). |

## 3. Data Schemas & Storage Contracts
### 3.1 Postgres schemas (`migrations/`)
- **`raw` schema (`raw_schema.sql`):** Stores source CourtListener artifacts.
  - `raw.opinions`: `id`, `cluster_id`, multiple text renditions, `record_json`, timestamps.
  - `raw.opinion_clusters`: filing metadata keyed by `cluster_id`, court, date filed.
- **`derived` schema (`derived_tables.sql`):** Normalized objects the app queries.
  - `derived.taxonomy_node`: Versioned taxonomy codes, labels, and synonym arrays.
  - `derived.legal_unit`: Atomic “legal units” (holdings/dicta snippets) tied to taxonomy codes, posture, circuit, favorability scores, and `source_opinion_id` lineage.
  - `derived.job_run`: Tracks ingestion jobs with `last_raw_id`, `batch_size`, status, and errors.
- **Taxonomy governance (`taxonomy_*.sql`):** Implements review queues, lifecycle states, and governance events so new codes from `taxonomy/<version>/taxonomy.yaml` can be staged, approved, retired, and aliased.
- **Admin/UI migrations (`admin_ui.sql`, `ingestion_guardrails.sql`):** Provision workspaces for the React/Next admin UI (in `admin_ui/`) and enforce ingestion quotas + health checks.

### 3.2 Ontology + taxonomy files
- `taxonomy/<version>/taxonomy.yaml`: Canonical catalog of issue codes (Fourth Amendment through procedural and evidence doctrines) with synonyms for tagging.
- `taxonomy/<version>/aliases.yaml`: Crosswalk for deprecated codes.

### 3.3 Vector store + embeddings
- Default embedding model: `all-MiniLM-L6-v2` (`acquittify/config.py`).
- Collection name: `acquittify_corpus`; distance metric `cosine`.
- Metadata enforced in `document_ingestion_backend.py` (`ALLOWED_METADATA_FIELDS`), covering provenance (case, court, docket), citation stats, taxonomy classification, chunk offsets, and file hashes for deduplication.

### 3.4 Workspace layout (local disk / S3 mirror)
```
<DATA_ROOT>/workspaces/<workspace_id>/<case_id>/
  documents/        # original uploads
  processed/        # chunked text
  chroma/           # vector store + metadata dumps
  transcripts/      # transcript ingest artifacts
  reports/          # structured outputs for UI
```
This mirrors into AWS S3 buckets per tenant tier with lifecycle policies (Standard → Standard-IA → Glacier) as described below.

## 4. Feature Overview
1. **Unified ingestion:**
   - Server-side ingestion workers handle PDFs, folders, ZIP bundles, transcript payloads, and caselaw sources with per-case routing and guardrails.
   - Backend auto-chunks, hashes, and writes into case workspaces, updates Chroma, and synthesizes metadata summaries via the taxonomy embedding agent + Ollama/Qwen.
2. **Transcript pipeline:** Dedicated chunkers (`acquittify/ingest/transcript_*`) keep speaker labels, page/line numbers, and courtroom phases intact for retrieval.
3. **Taxonomy-driven retrieval:**
   - Tagging via `taxonomy_embedding_agent` enriches each chunk with primary + secondary codes, authority weights, and Bluebook-safe citations.
   - API/worker services consume the YAML taxonomy to drive search filters, ontology graphs, and review workflows.
4. **Server automations:**
   - API and batch services handle bootstrapping, PDF/Office parsing, transcript processing, prompt contracts, and OpenClaw agent plumbing (including `OPENCLAW_GATEWAY_TOKEN`, rate limits, and session caching).
5. **Nightly data feeds:**
   - `incourt_listener/`, `trial-discovery-ai/`, and `scripts/` host CAP + CourtListener importers, with launchd plists checked into `scripts/com.acquittify.*.plist` for scheduling.
6. **Brand + compliance:**
   - Prompt contracts, policy docs, and `LEGAL_UNIT_CONTRACT.md` define Bluebook-aware citation and legal-unit mapping requirements for downstream client outputs.

## 5. Pricing, Token, and Storage Limits (customer-facing)
_Assumes OpenAI `gpt-5.1/5.2-codex` pricing at ~$0.010 / 1K input tokens and ~$0.030 / 1K output tokens. Storage costs blend AWS S3 Standard ($0.023/GB-month) + 30% overhead for versioning/egress → **$0.03/GB-month** internal cost basis._

| Tier | Monthly price | Included tokens | Included storage (AWS S3) | Rate limits | Token overage | Storage overage |
| --- | --- | --- | --- | --- | --- | --- |
| **Starter / Beta** | $19 (or free invite-only) | 50,000 tokens/month | 5 GB (≈2,500 PDFs or transcripts) | 3 req/min, burst 10; hard stop at 50k tokens | Not available – prompt upgrade | $0.25/GB-month beyond 5 GB |
| **Pro** | $59 | 300,000 tokens/month | 50 GB with 30-day version history | 5 req/min, burst 20; warn at 250k, cap at 300k | $15 per +100k tokens | $0.18/GB-month beyond 50 GB |
| **Enterprise** | Custom (starts ~$249) | 1,000,000+ pooled tokens/month | 200 GB+ with Standard → IA → Glacier lifecycle | Default 10 req/min, burst 40 (tunable per tenant) | Contracted (e.g., $10 per +100k tokens) | Custom; option to tier older data to IA/Glacier |

**Daily per-user caps:** 50k tokens (Starter), 150k (Pro), custom for Enterprise. Breaching the daily cap shifts users into “slow mode” (1 req/min) until the next UTC day.

**Storage lifecycle:**
- >90 days: move to S3 Standard-IA unless pinned by the user.
- >365 days: move to Glacier Deep Archive unless workspace opts out.
- Trash + duplicate revisions purge after 30 days; maximum 5 historical versions per document count toward quota.

**Alerts:** Email admins (and in-app banners) at 70% and 90% of either quota. Billing exports include token + storage line items so tenants see what triggered charges or throttling.

## 6. Suggested Document Placement & Next Steps
- File stored at `docs/acquittify_app_brief.md` so it can anchor the empty architecture stubs (`docs/architecture/*.md`).
- Future tasks:
  1. Backfill the empty architecture chapter files with more detail (can excerpt sections from this brief).
  2. Wire the pricing + quota table into the admin UI (`admin_ui/`), using `derived.job_run` + S3 metrics for live dashboards.
  3. Keep this brief updated whenever taxonomy versions, models, or pricing change (note the date stamp above).
