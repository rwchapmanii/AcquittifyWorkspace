# Local/Desktop Data Control Roadmap

## Goal

Ship local and desktop builds where users have full control of their data, with no unintended cross-user visibility and no silent cloud upload.

## Principles

- user-owned data stays on local disk by default
- outbound network use is explicit and user-controlled
- no shared/global storage paths for user artifacts
- every read/write/query is scoped to a selected local workspace/profile

## Current Gaps (from code)

- shared admin upload path: `Corpus/Raw/AdminUploads` in `admin_ui/main.py`
- shared vector path: `Corpus/Chroma` in `admin_ui/main.py`
- hardcoded processed case path: `Corpus/Processed/<case>` in `document_ingestion_backend.py`
- single global vault root (`VAULT_ROOT`) in `AcquittifyElectron/main.js`

## Milestone 1 - Storage Root and Workspace Boundaries

### Scope

- introduce one canonical `data_root` for local/desktop runtime
- eliminate hardcoded corpus paths in user-facing flows
- define local workspace/profile identity (`workspace_id`)

### Implementation Tasks

- [x] add settings model: `data_root`, `workspace_id`, `offline_mode`
- [x] update ingestion code to accept explicit workspace root
- [x] replace direct `Corpus/...` writes with `data_root/workspaces/<workspace_id>/...` in core ingestion/admin flows
- [x] add path validation helper: all file operations must remain inside workspace root

### Current M1 Status

- [x] `acquittify/local_workspace.py` added (`data_root`, `workspace_id`, boundary checks)
- [x] `document_ingestion_backend.py` scoped to workspace-local case roots
- [x] `document_ingestion_ui.py` supports explicit `workspace_id`
- [x] `admin_ui/main.py` moved admin uploads/chroma/case logs under workspace root
- [x] `AcquittifyElectron/main.js` now resolves workspace-scoped defaults and stores per-workspace vault roots
- [ ] add automated tests for path traversal and workspace boundary enforcement
- [ ] migrate remaining non-core scripts still pointing at legacy `Corpus/` and `Casefiles/`

### Primary Files

- `admin_ui/main.py`
- `document_ingestion_backend.py`
- `document_ingestion_ui.py`
- `AcquittifyElectron/main.js`

### Exit Criteria

- no user-content writes to global `Corpus/*` paths
- user can switch local workspace without seeing other workspace data
- path traversal tests fail closed

## Milestone 2 - Tenant-like Isolation for Local Profiles

### Scope

- add strict per-workspace scoping to metadata, retrieval, and chat history
- prevent cross-workspace lookups by ID/path

### Implementation Tasks

- include `workspace_id` in stored metadata for documents/chunks
- apply workspace filter to every retrieval query
- namespace session/history stores by workspace
- reject any request where target object workspace != active workspace

### Primary Files

- `document_ingestion_backend.py`
- `acquittify/` retrieval and metadata modules
- `AcquittifyElectron/main.js`
- `admin_ui/main.py`

### Exit Criteria

- integration tests prove workspace A cannot retrieve workspace B content
- duplicate IDs across workspaces do not collide
- audit logs include `workspace_id`

## Milestone 3 - Network and Privacy Controls

### Scope

- add explicit controls for network egress and telemetry
- make offline mode first-class for local/desktop

### Implementation Tasks

- add outbound network guard with allowlist
- gate remote features behind explicit user toggle
- add UI indicators before any remote call
- ensure telemetry/analytics defaults to off for local build

### Primary Files

- `AcquittifyElectron/main.js`
- network-call sites in ingestion/retrieval modules
- settings UI files under `AcquittifyElectron/ui/`

### Exit Criteria

- offline mode blocks non-local network calls
- remote APIs are only used when user enabled
- no hidden background upload behavior

## Milestone 4 - Data Lifecycle Controls (Export, Delete, Restore)

### Scope

- give users complete lifecycle control over local data
- support upgrade-safe restore with schema/version checks

### Implementation Tasks

- implement `Export Workspace` (zip all workspace artifacts)
- implement `Delete Workspace Data`
- implement `Import/Restore Workspace`
- add migration version manifest for workspace data

### Primary Files

- `AcquittifyElectron/main.js`
- `AcquittifyElectron/ui/app.js`
- shared utility modules for file/archive operations

### Exit Criteria

- export -> clean install -> restore returns same document count and searchability
- delete fully removes workspace artifacts
- incompatible restore versions fail with clear error

## Milestone 5 - Packaging, Hardening, and Release Gates

### Scope

- finalize desktop builds with secure defaults and release checks
- publish user-facing data control documentation

### Implementation Tasks

- enforce secure defaults in production build config
- sign/notarize desktop builds
- add release checklist with privacy/security gates
- publish in-app "Data Control" page (what is local, what is remote)

### Primary Files

- `AcquittifyElectron/package.json`
- build/release scripts
- `README.md` and docs pages

### Exit Criteria

- release checklist passes in CI
- security review confirms local-data contract
- docs match runtime behavior

## Test Plan (Required Before GA)

- unit: path sandboxing and workspace resolution helpers
- integration: ingestion/retrieval isolation across 2+ workspaces
- integration: offline mode network-block behavior
- e2e: export/delete/restore round trip
- regression: existing local workflows continue to function

## Execution Order

1. Milestone 1
2. Milestone 2
3. Milestone 3
4. Milestone 4
5. Milestone 5

Do not start Milestone 3 before Milestone 1 and 2 are in place.
