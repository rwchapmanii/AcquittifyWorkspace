## MVP elevator pitch

This MVP is a **defense-only, trial-first discovery intelligence system** that ingests documents from **Dropbox** (source of truth), generates **immutable factual metadata** (who/what/when/how) and **contextual signals** (events, entities, privilege risk, statement structure), then runs an **Exhibit + Hot Doc Prioritization pass** that assigns every document a simple **P1–P4 attention code** (Must Read → Disregard) with short, citeable reasons. Reviewers can mark documents as **Hot** and **Exhibit**, and the system gets smarter **within the matter** by learning from those selections to reprioritize other documents—without ever rewriting the factual record. The UI is built around **witness prep and exhibits**, not review queues: you can open a witness, see the top P1 documents tied to them, build an exhibit list by purpose (impeachment/timeline/bias), and export trial-ready binders and lists. Everything is **auditable, versioned, reproducible**, and architected so you can plausibly defend the methodology later (Daubert track) because each “pass” is separated, logged, and bounded in what it’s allowed to infer.

---

# MVP spec for implementation in VS Code

What follows is written as a **build contract**: repo structure, services, schemas, passes, and the order to implement. If you keep to this, you won’t drift into “Relativity clone hell.”

---

## 1) Product constraints and guardrails

### Defense-only and trial-first

* Primary outputs are **(a) hot-doc prioritization, (b) exhibit candidates, (c) witness-centered navigation**.
* Motions/production/review queues are out of MVP scope.

### Epistemic separation by passes (non-negotiable)

* **Pass 1** = facts only, immutable (chain-of-custody + objective extraction)
* **Pass 2** = signals, cached (events, statement structure, privilege likelihood, entity enrichment)
* **Pass 3** = on-demand trial intelligence (optional MVP+)
* **Pass 4** = exhibit/hot-doc prioritization + learning (attention allocation only)

### Learning is “attention learning,” not “truth learning”

* The system learns what a team tends to treat as hot/exhibit-worthy **within this matter**.
* Learning must never rewrite Pass 1/2.

### Reproducibility

* Every inference stores: model id/version, prompt hash/version, input artifact hashes, timestamp, settings, and output JSON.
* Pass 1 runs at deterministic settings (temperature 0).

---

## 2) Tech stack (MVP-feasible, scalable later)

### Backend

* **Python 3.12**
* **FastAPI** (API + auth endpoints)
* **PostgreSQL** (metadata + audit) + **pgvector** (embeddings)
* **Redis** (job broker/cache)
* **Celery** (async pipeline workers)

### Artifacts

* Dropbox is source-of-truth for originals, but you still need fast internal derived artifacts:

  * **MinIO (S3-compatible)** for: page images, extracted text JSON, normalized email JSON, thumbnails
* Store only *references* in Postgres.

### Document processing

* PDF rendering: `pymupdf` (fitz) or `poppler` wrapper
* OCR: `tesseract` via `pytesseract` (MVP)
  (swap later for better OCR, but MVP works)
* Office conversion: LibreOffice headless (MVP) or defer
* Email parsing: `mailparser` for `.eml` (MVP)

### Frontend

* **Next.js (TypeScript)** or **React + Vite**
  (Next.js is nicer for auth + routing + SSR doc viewer)
* PDF viewer: `pdf.js`
* Image viewer for page images + highlight overlays (later)

### LLM

* Abstract behind an interface so you can swap models/providers per pass.
* Enforce JSON schema outputs via Pydantic validation.

---

## 3) Repo layout (copy this into your VS Code project)

```
trial-discovery-ai/
  docker-compose.yml
  .env.example
  README.md

  backend/
    pyproject.toml
    app/
      main.py
      core/
        config.py
        logging.py
        security.py
        llm/
          client.py          # provider abstraction
          prompts.py         # prompt registry + versioning
          schemas.py         # pydantic output schemas per pass
          validate.py        # strict JSON validation + repair
        storage/
          s3.py              # MinIO client
          dropbox.py         # Dropbox client + cursor management
        db/
          session.py
          migrations/
          models/
            matter.py
            document.py
            artifact.py
            chunk.py
            pass_run.py
            user_action.py
            exhibit.py
            entity.py
          repo/
            documents.py
            passes.py
            search.py
      services/
        ingest.py
        preprocess.py
        chunking.py
        embedding.py
        pass1.py
        pass2.py
        pass4.py
        learning.py
      api/
        routes/
          auth.py
          matters.py
          documents.py
          search.py
          passes.py
          exhibits.py
          witnesses.py
      workers/
        celery_app.py
        tasks.py
        pipelines.py

  frontend/
    package.json
    next.config.js
    src/
      pages/
        index.tsx
        matters/[id].tsx
        matters/[id]/hotdocs.tsx
        matters/[id]/exhibits.tsx
        matters/[id]/witnesses.tsx
        docs/[docId].tsx
      components/
        DocViewer.tsx
        PriorityBadge.tsx
        ExhibitPanel.tsx
        WitnessList.tsx
        SearchBar.tsx
        Filters.tsx

  docs/
    MVP_SPEC.md            # paste this spec here
    PROMPT_CONTRACTS.md
    DATA_MODEL.md
```

---

## 4) System architecture (how data flows)

### Ingestion → processing → indexing → prioritization

1. **Dropbox ingest**

   * Pull file metadata + bytes (or download links)
   * Create `documents` + `document_versions`
   * Compute `sha256`
   * Create `artifacts` placeholders
   * Enqueue preprocess pipeline

2. **Preprocess**

   * Convert to canonical representation:

     * PDFs → page images + extracted text (OCR only if needed)
     * EML → normalized JSON (headers, body, attachments)
     * Office → PDF + same pipeline (optional MVP)
   * Store derived artifacts in MinIO

3. **Chunk + embed**

   * Chunk extracted text into segments
   * Store `chunks` + embeddings (pgvector)

4. **Pass 1**

   * Produce immutable factual metadata + audit

5. **Pass 2**

   * Produce contextual signal metadata + audit

6. **Pass 4**

   * Produce P1–P4 priority codes + exhibit candidates + rationale
   * Initialize learning state

7. **User actions**

   * Hot-doc / Exhibit marks + promotions/demotions
   * Stored as immutable `user_actions`
   * “Re-score” button triggers reprioritization job (learning)

---

## 5) Data model (practical, indexable, versioned)

### Key design: “latest view” is derived, history is preserved

* Don’t update inference rows in place.
* Insert a new `pass_run` for each execution, mark it as latest.

### Core tables (MVP minimum)

#### matters

* `id (uuid)`
* `name`
* `created_by`
* `created_at`
* `dropbox_root_path`
* `settings_json` (project parameters, trial posture toggles, etc.)

#### documents

* `id (uuid)`
* `matter_id`
* `source_path`
* `original_filename`
* `mime_type`
* `sha256`
* `file_size`
* `page_count`
* `ingested_at`
* `status` (enum: NEW, PREPROCESSED, INDEXED, READY, ERROR)
* indexes: `(matter_id)`, `(sha256)`, `(matter_id, status)`

#### artifacts

* `id (uuid)`
* `document_id`
* `kind` (enum: PAGE_IMAGE, EXTRACTED_TEXT, OCR_TEXT, EMAIL_JSON, THUMBNAIL)
* `uri` (s3://…)
* `content_hash`
* `created_at`

#### chunks (for vector search)

* `id (uuid)`
* `document_id`
* `page_num` (nullable)
* `chunk_index`
* `text`
* `start_offset` / `end_offset` (nullable)
* `embedding vector(1536|3072|provider-dependent)`
* indexes: `ivfflat/hnsw on embedding`, `(document_id)`

#### pass_runs (one row per pass execution per document)

* `id (uuid)`
* `document_id`
* `pass_num` (1,2,3,4)
* `model_id`
* `model_version`
* `prompt_id`
* `prompt_hash`
* `settings_json` (temperature, etc.)
* `input_artifact_hashes_json`
* `output_json` (JSONB, validated)
* `status` (SUCCESS/FAIL/REPAIRED)
* `created_at`
* `is_latest` (bool)
* indexes: `(document_id, pass_num, is_latest)`, `(pass_num, is_latest)`

#### entities (resolved people/orgs)

* `id (uuid)`
* `matter_id`
* `entity_type` (PERSON/ORG)
* `canonical_name`
* `aliases_json`
* `created_at`

#### document_entities (many-to-many)

* `document_id`
* `entity_id`
* `role` (AUTHOR/SENDER/RECIPIENT/MENTIONED/SIGNATORY)
* `confidence`

#### exhibits (human-confirmed)

* `id (uuid)`
* `matter_id`
* `document_id`
* `marked_by`
* `purpose` (IMPEACHMENT/TIMELINE/BIAS/SUBSTANTIVE/FOUNDATION)
* `notes`
* `created_at`

#### user_actions (learning signals, immutable)

* `id (uuid)`
* `matter_id`
* `document_id`
* `user_id`
* `action_type`

  * VIEW
  * MARK_HOT
  * UNMARK_HOT
  * PRIORITY_OVERRIDE (from,to)
  * MARK_EXHIBIT
  * UNMARK_EXHIBIT
  * EXPORT
* `payload_json` (e.g., override values)
* `created_at`

---

## 6) Metadata ontology mapped to passes (complete MVP set)

This is the **contract** your LLM outputs must satisfy.

### Pass 1 output schema (facts only, immutable)

**Goal:** “What is this document, mechanically?”

Fields:

* `doc_identity`

  * `source_path`, `original_filename`, `mime_type`, `sha256`, `file_size`, `page_count`
* `doc_type`

  * `category` (EMAIL/PDF/SPREADSHEET/PLEADING/CONTRACT/REPORT/NOTES/CHAT/OTHER)
  * `draft_final` (DRAFT/FINAL/UNKNOWN)
  * `internal_external` (INTERNAL/EXTERNAL/UNKNOWN)
  * `domain` (BUSINESS/LEGAL/REGULATORY/UNKNOWN)
* `authorship_transmission` (nullable parts allowed)

  * `author_names[]`
  * `sender`
  * `recipients_to[]`, `recipients_cc[]`, `recipients_bcc[]`
  * `organizations[]` (raw strings)
* `time`

  * `system_created_at`, `system_modified_at`
  * `sent_at` (emails)
  * `dates_mentioned[]` (raw strings + normalized if obvious)
* `entities_raw`

  * `people_mentioned[]`
  * `orgs_mentioned[]`
* `quality`

  * `ocr_used` bool
  * `ocr_confidence_overall`
  * `parsing_confidence_overall`

### Pass 2 output schema (signals, cached)

**Goal:** “What is going on in this doc, structurally?”

Fields:

* `doc_subtype` (more specific classification)
* `entities_enriched`

  * resolved entity candidates with confidence
  * role hypotheses (DECISION_MAKER/MESSENGER/etc.)
* `events[]`

  * `event_type`, `date`, `participants[]`, `summary`, `confidence`
* `statements[]` (lightweight segmentation)

  * `text_span_ref` (offsets or chunk refs)
  * `statement_type` (FACT/OPINION/INSTRUCTION/DENIAL/QUESTION/COMMITMENT)
  * `speaker` (if inferable)
  * `certainty` 0–1
  * `first_hand_likelihood` 0–1
* `knowledge_signals[]`

  * `type` (ASSERTED/DENIED/IMPLIED)
  * `about` (topic)
  * `time_ref` (if any)
  * `confidence`
* `privilege_sensitivity`

  * `attorney_involved` bool + confidence
  * `legal_advice_likelihood` 0–1
  * `work_product_likelihood` 0–1
  * `pii_flags[]`
* `generic_trial_signals`

  * `trial_relevance_hint` 0–1 (NOT an ultimate relevance claim)
  * `govt_reliance_likelihood` 0–1
  * `defense_value_likelihood` 0–1
  * `redundancy_hint` 0–1
  * `jury_readability_hint` 0–1

### Pass 4 output schema (exhibit + hot doc prioritization)

**Goal:** “Where should lawyers spend time?”

Fields:

* `priority_code` (P1/P2/P3/P4)
* `priority_rationale` (max ~5 bullets; each bullet should point to evidence spans/chunks)
* `hot_doc_candidate` bool + confidence
* `exhibit_candidate`

  * `is_candidate` bool
  * `purposes[]` (IMPEACHMENT/TIMELINE/BIAS/SUBSTANTIVE/FOUNDATION)
  * `foundation_needed_hint` bool
  * `backfire_risk_hint` 0–1
  * `likely_objection_hints[]` (non-authoritative tags)
* `similarity_hooks`

  * key terms/entities/events used to find “docs like this”

### Pass 3 (optional MVP+) on-demand witness output

**Goal:** “Prep this witness for trial.”

Fields:

* `witness_profile`
* `themes`
* `top_docs[]` (doc_id + why)
* `impeachment_candidates[]`
* `contradiction_candidates[]` (conservative; cite both docs)
* `silence_points[]` (only if the system can cite “expected document class missing”)

---

## 7) LLM implementation contract (so VS Code + GPT can code it)

### Hard requirement: schema-first JSON outputs

* Define Pydantic models for each pass output (Pass1Schema, Pass2Schema, Pass4Schema).
* LLM must return JSON that validates **exactly**.
* If validation fails:

  1. store raw response in `pass_runs` as FAIL
  2. run `validate.repair_json()` (a “repair prompt”) with the same or stronger model
  3. store repaired output as REPAIRED or FAIL

### Prompt versioning

* Every prompt has:

  * `prompt_id` (e.g., `pass1_v1`)
  * `prompt_hash` (sha256 of final prompt text)
* Store both in `pass_runs`.

### Determinism

* Pass 1 uses `temperature=0`, `top_p=1`.
* Pass 2 can use `temperature=0` for consistency.
* Pass 4 can use low temperature (0–0.2), but still should be stable.

### Evidence references

MVP-friendly approach:

* Passes refer to **chunk IDs** (and optionally page numbers).
* Example: `"evidence": [{"chunk_id": "...", "quote": "…"}]`

Avoid bounding boxes in MVP; add later.

---

## 8) Pass pipeline orchestration (Celery chain)

Create a single pipeline function per document:

`pipelines.process_document(document_id)`

Celery task chain:

1. `tasks.preprocess(document_id)`
2. `tasks.chunk_and_embed(document_id)`
3. `tasks.run_pass1(document_id)`
4. `tasks.run_pass2(document_id)`
5. `tasks.run_pass4(document_id)`
6. `tasks.update_document_status(document_id, READY)`

All tasks must be idempotent:

* If artifacts exist with same hashes, skip regeneration.

---

## 9) Exhibit + hot doc learning (MVP-feasible and effective)

### Learning behavior (MVP)

* Learning is triggered **only when user clicks “Re-score using my hot docs”**.
* It produces a **new Pass 4 run** (don’t mutate the old one).

### Learning method (implementable now)

Use a hybrid of:

1. **Similarity lift**

   * Take embeddings of user-marked hot docs (and/or exhibits)
   * Compute centroid vector
   * Score remaining docs by cosine similarity
2. **Feature lift**

   * Use Pass 2/4 features (authority hints, event anchors, govt reliance likelihood, jury readability)
   * Apply a simple weighted scoring function
3. Combine into an updated priority suggestion

This avoids building full ML infra in MVP but still “feels” adaptive.

### What you store

* A matter-level `learning_state` JSON in `matters.settings_json` or separate table:

  * `hot_doc_doc_ids[]`
  * `centroid_embedding` (optional cached)
  * `feature_weights_version`
  * `last_rescore_at`

### Guardrails

* Never auto-demote user-marked hot docs (human wins).
* Always include “why reprioritized” (e.g., “similar to hot docs you marked; shares entity X and event Y”).

---

## 10) API endpoints (minimal set to build the UI)

### Matters

* `POST /matters` create
* `GET /matters`
* `GET /matters/{id}`

### Ingestion

* `POST /matters/{id}/ingest/start` (start Dropbox sync/poll)
* `GET /matters/{id}/ingest/status`

### Documents

* `GET /matters/{id}/documents?filters...`
* `GET /documents/{docId}` (metadata + latest pass outputs)
* `GET /documents/{docId}/artifacts` (page images, extracted text)
* `POST /documents/{docId}/actions` (mark hot, mark exhibit, override priority)

### Search

* `GET /matters/{id}/search?q=...&filters...` (hybrid search results)
* `GET /matters/{id}/hotdocs` (P1/P2 sorted)

### Exhibits

* `GET /matters/{id}/exhibits`
* `POST /matters/{id}/exhibits/export` (CSV/JSON export)

### Learning / Rescore

* `POST /matters/{id}/priorities/rescore` (creates new Pass 4 run batch)

### Witnesses (MVP simple)

* `GET /matters/{id}/witnesses` (top entities by frequency/centrality)
* `GET /matters/{id}/witnesses/{entityId}/documents` (filter docs by entity)
* Optional MVP+: `POST /witnesses/{entityId}/prep` (Pass 3 on-demand)

---

## 11) Frontend screens (trial-native, minimal, shippable)

### Matter dashboard

* ingestion status
* “Hot Docs” button
* “Exhibits” button
* “Witnesses” button
* global search bar

### Hot Docs screen

* list view with:

  * Priority badge (P1–P4)
  * Exhibit candidate icon
  * quick actions: Mark Hot, Mark Exhibit, Override Priority
* filters: doc type, date range, sender/recipient, exhibit-only

### Document viewer screen

* left: doc info + entity chips
* center: PDF/image viewer + extracted text toggle
* right: Pass tabs

  * Pass 1 facts
  * Pass 2 signals
  * Pass 4 priority + exhibit rationale
* actions: Mark Hot, Mark Exhibit, Override Priority, Add note

### Exhibits screen

* grouped by purpose and/or witness
* export list
* “confirm exhibit” flow

### Witnesses screen (MVP simple)

* list of people (ranked)
* clicking a witness filters hot docs to those tied to witness
* MVP+: generate witness prep summary

---

## 12) Feasibility notes (what’s hard, what we deliberately postpone)

### Hard but feasible in MVP

* PDF rendering + OCR pipeline
* EML parsing
* Embeddings + pgvector hybrid retrieval
* Pass-based metadata extraction with strict schemas
* Exhibit prioritization and matter-scoped adaptive reprioritization

### Postponed on purpose (to keep MVP buildable)

* Full Relativity-style productions and privilege logs
* MSG/PST ingestion at scale (start with EML; add PST later)
* Perfect table extraction from spreadsheets
* Bounding-box citations (start with chunk IDs + page numbers)
* Firm-wide learning (matter-scoped only in MVP)

---

# 13) “Keep us on track” build order checklist

If you follow this sequence, you will ship the wedge without getting lost.

### Step 1 — Skeleton + dev environment

* docker-compose: postgres + redis + minio
* FastAPI healthcheck
* Next.js skeleton with auth stub

### Step 2 — Data model + migrations

* create tables above
* implement repositories for documents/pass_runs

### Step 3 — Dropbox ingest service

* pull file list from root path
* create documents + enqueue pipeline per file

### Step 4 — Preprocess pipeline (PDF/EML first)

* store artifacts to MinIO
* extracted text into JSON

### Step 5 — Chunk + embed

* implement chunker
* store chunks + embeddings

### Step 6 — Pass 1 implementation

* prompt + schema + validator
* write pass_run

### Step 7 — Pass 2 implementation

* prompt + schema + validator
* write pass_run

### Step 8 — Pass 4 implementation (priority + exhibits)

* prompt + schema + validator
* compute P1–P4 + rationale

### Step 9 — UI hot docs + viewer

* hot docs list
* doc viewer with pass tabs
* mark hot/exhibit + priority override

### Step 10 — Learning (explicit rescore)

* store actions
* implement rescore endpoint
* generate new pass 4 runs

### Step 11 — Witness list (simple)

* compute top entities
* filter docs by witness

### Step 12 — Exports

* exhibit list export (CSV/JSON)

That’s the MVP.

---

## 14) Definition of done (so you know when MVP is “real”)

A matter is “ready” when:

* You ingest a Dropbox folder and see documents in the UI
* Every document has:

  * Pass 1 output
  * Pass 2 output
  * Pass 4 priority + exhibit candidate
* Hot Docs screen shows P1s first with reasons
* Reviewer can mark:

  * Hot
  * Exhibit
  * Override priority
* Clicking “Re-score” reprioritizes additional docs in a way that is:

  * explainable
  * consistent
  * matter-scoped
* You can export an exhibit list

---

## If you want, I can generate the first code artifacts next
