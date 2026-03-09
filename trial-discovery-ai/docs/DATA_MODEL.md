# Data Model (MVP)

## Core tables

- `matters`
- `documents`
- `artifacts`
- `chunks`
- `pass_runs`
- `entities`
- `document_entities`
- `exhibits`
- `user_actions`

## Enums

- `document_status`
- `artifact_kind`
- `pass_status`
- `entity_type`
- `document_entity_role`
- `exhibit_purpose`
- `user_action_type`

## Indexes

- `documents` on `matter_id`, `sha256`, `(matter_id, status)`
- `chunks` on `document_id`
- `pass_runs` on `(document_id, pass_num, is_latest)` and `(pass_num, is_latest)`

## Migrations

- Alembic in `backend/app/db/migrations`
- Initial schema in `0001_initial.py`
