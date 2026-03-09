# Admin Review UI (Offline-Only)

## Purpose
This UI is an internal, offline-only tool for lawyer-developers to inspect system behavior. It supports read-only inspection and explicit review event creation. It does not mutate production tables directly.

## What humans can review
- **Taxonomy Explorer**: view taxonomy nodes with usage counts and primary/secondary usage rates.
- **Legal Unit Browser**: audit legal units with filters and metadata.
- **Intent Audit Viewer**: review deterministic routing decisions recorded in the database.
- **Taxonomy Gap Dashboard**: surface high-signal gaps and review queue entries.
- **Taxonomy Gap Events**: view raw gap events with filters.

## What humans cannot directly change
- **No taxonomy mutations**: nodes are not edited or created in the UI.
- **No legal unit editing**: legal unit text is immutable in the UI.
- **No automatic changes**: nothing is updated without explicit review events.

## Taxonomy lifecycle governance
Taxonomy nodes carry a lifecycle status: ACTIVE, EXPERIMENTAL, or DEPRECATED. Deprecated nodes remain queryable for legacy units but are not permitted for new review assignments.

## Review actions (events only)
Review actions create rows in `derived.taxonomy_review_event` only. These events are used for offline governance workflows and do not automatically update taxonomy data.

## API endpoints (v1)
Read-only:
- GET /api/taxonomy/tree
- GET /api/taxonomy/node/{code}/legal-units
- GET /api/legal-units
- GET /api/intent-audit
- GET /api/taxonomy-gaps
- GET /api/taxonomy-gap-events

Review events (writes only to event tables):
- POST /api/legal-units/{unit_id}/flag-review
- POST /api/taxonomy-gaps/{gap_id}/review-action

## Database roles
- **Read-only**: used for all GET endpoints and UI views.
- **Reviewer (write)**: used only to insert review events.

Set environment variables:
- `ACQUITTIFY_DB_DSN_READONLY`
- `ACQUITTIFY_DB_DSN_WRITE`

## Local auth
Authentication uses a local `derived.admin_user` table with hashed passwords. Roles:
- `read_only`
- `admin_reviewer`

## Migrations
Apply the following SQL migrations:
- `migrations/derived_tables.sql`
- `migrations/taxonomy_governance.sql`
- `migrations/taxonomy_gap_event_updates.sql`
- `migrations/admin_ui.sql`
- `migrations/taxonomy_lifecycle.sql`
- `migrations/ingestion_guardrails.sql`

## Docker Compose
The UI is served via Docker Compose. See docker-compose.yml at the repository root.

## Safe taxonomy promotion
Taxonomy version changes are performed by explicit SQL migrations and offline review workflows. The UI only records review events.
