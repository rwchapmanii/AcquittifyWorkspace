# Acquittify / Federal Defense AI — Copilot Instructions

## Non-negotiables
- Do NOT modify raw CourtListener ingest tables. Treat schema `raw` as immutable.
- All database changes must be done via migrations (no manual edits).
- New derived tables live in schema `derived`.
- Every retrievable unit must include: circuit, year, posture, SoR, burden, is_holding/is_dicta, favorability, taxonomy codes.
- Do not embed full opinions. Only embed derived.legal_unit chunks.

## Coding rules
- Prefer adding new modules/services over refactoring existing working code.
- Keep changes small (one feature per commit).
- Add tests for every new module.
- If unsure, ask for clarification in code comments rather than guessing.

## Build / Run
- Use docker compose for local services.
- Provide exact commands to run migrations, tests, and the app.
