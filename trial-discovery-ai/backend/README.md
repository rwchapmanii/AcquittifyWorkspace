# Acquittify Peregrine Backend

Backend service for the Peregrine MVP (federal criminal defense discovery review).

## Authentication
- `POST /auth/register` creates a user, organization, membership, and session cookie.
- `POST /auth/login` issues a session cookie.
- `GET /auth/me` returns the authenticated user + organization context.
- `POST /auth/logout` clears the session cookie.
- `POST /auth/password/forgot` issues a password reset token.
- `POST /auth/password/reset` sets a new password using a valid reset token.

## Authorization and Security
- RBAC roles: `owner`, `admin`, `editor`, `viewer`.
- Write endpoints require at least `editor`; admin-only endpoints require `admin`.
- CSRF protection is enabled for unsafe HTTP methods when a session cookie is present.
  Frontend must send the CSRF header (`X-CSRF-Token` by default) with mutating requests.
- Auth endpoints (`/auth/login`, `/auth/register`, `/auth/password/*`) are rate-limited.

All non-health/version API routes require authentication and are scoped to the
authenticated organization.

## Container deployment

- Backend image: `trial-discovery-ai/backend/Dockerfile`
- Worker process uses the same image with:
  - `celery -A app.workers.celery_app.celery_app worker`
- Phase 3 stack (API + worker + frontend) is defined in:
  - `deploy/docker-compose.phase3.yml`

## Ingest flow (Dropbox → parse → chunk/embed → passes)
1. **Dropbox ingest**: `POST /matters/{id}/ingest/start` in
	[app/api/routes/ingest.py](app/api/routes/ingest.py) creates `Document` rows and
	enqueues the pipeline.
2. **Pipeline**: [app/workers/tasks.py](app/workers/tasks.py) runs
	`preprocess → chunk_and_embed → pass1 → pass2 → pass4`.
3. **Preprocess/parsing**: [app/services/preprocess.py](app/services/preprocess.py)
	extracts text + metadata for PDF/EML/DOCX/XLSX/images and stores
	`EXTRACTED_TEXT` artifacts in S3. It also records:
	- OCR usage + OCR confidence per page
	- Language detection
	- Normalized SHA-256 + Simhash (near-dup clustering)
	- Privilege term signals
4. **Chunking + embeddings**: [app/services/chunking.py](app/services/chunking.py)
	uses boundary-aware chunking (paragraph/sentence breaks) with overlap.
	[app/services/chunk_and_embed.py](app/services/chunk_and_embed.py) creates:
	- **Document-level summary chunk** (`chunk_index = -1`)
	- **Page-level chunks** with embeddings
	Embedding input is **augmented** with a metadata header to improve recall.

## Embedding context (recall “marking”)
Embedding headers and summaries are built in
[app/services/embedding_context.py](app/services/embedding_context.py). The header
includes document id, matter id, filename, source path, doc type, language,
hashes, and key email metadata (when applicable), then the chunk text is appended.

## Hybrid search (lexical + vector)
`POST /matters/{id}/search` in
[app/api/routes/search.py](app/api/routes/search.py) uses reciprocal-rank fusion
over:
- vector similarity (pgvector cosine distance)
- lexical ranking (Postgres `websearch_to_tsquery` over chunk text)

## Local services (avoid password mismatches)
Use the repo root .env as the single source of truth for compose credentials.
Peregrine services are defined in [docker-compose.peregrine.yml](../docker-compose.peregrine.yml)
and will load .env automatically when run from the repo root.

If you change Postgres credentials, reset the volume to avoid stale passwords
and update `DATABASE_URL` in [backend/.env](.env) to match the port/user/pass.

## Sanity check for embedding changes
Run [scripts/sanity_check_embedding_context.py](scripts/sanity_check_embedding_context.py)
to preview embedding headers/summary and optionally call the embedding API:

```
python scripts/sanity_check_embedding_context.py <document_id>
python scripts/sanity_check_embedding_context.py <document_id> --run-embedding
```

## Dropbox Business team access
If the Dropbox app is a team app, set `DROPBOX_TEAM_MEMBER_ID` in
`backend/.env` to select the user context.

## Casefile sync from Dropbox
Case folders under `DROPBOX_CASE_ROOT_PATH` (e.g., `/Chapman Law Firm`) can be
synced into Peregrine matters (casefiles).

- One-time sync + print names:
	- [scripts/sync_dropbox_case_folders.py](scripts/sync_dropbox_case_folders.py)
		- `--print-only` prints folder names
		- default creates missing matters and sets `dropbox_root_path`
- Continuous watcher for new folders:
	- [scripts/watch_dropbox_case_folders.py](scripts/watch_dropbox_case_folders.py)
		- polls every N seconds and creates new casefiles

The casefile dropdown is backed by `GET /matters` in
[app/api/routes/matters.py](app/api/routes/matters.py); after sync, the list is
populated automatically.
