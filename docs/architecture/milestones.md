## Milestone 1 — DB foundations

- raw schema present, read-only to app user
- derived.taxonomy_node exists
- derived.legal_unit exists + indexed
- migrations repeatably apply

## Milestone 2 — Taxonomy loader

- taxonomy YAML loads into derived.taxonomy_node
- prefix queries work (4A.* etc.)

## Milestone 3 — “Walking skeleton” retrieval without vectors

- given a taxonomy code + circuit, return top N legal_units from Postgres

## Milestone 4 — Intent service v1 (rules only)

- takes user input → outputs intent JSON schema (even if confidence is lower)

## Milestone 5 — Vector stores + indexing worker

- Qdrant (or your vector DB) running in docker compose
- indexes one store (e.g., vs_legal_standard) from derived units

## Milestone 6 — Full routing pipeline

- intent → store selection → metadata filtering → vector search → rerank → context pack

## Milestone 7 — UI workflows

- suppression, sentencing, appeal screens show drill-down results
