# Precedent Ontology Compiler

This compiler turns an opinion into citation-anchored ontology artifacts in an Obsidian-style vault.

## Governing documents

- Blueprint authority: Citation-Anchored Precedential Ontology in YAML (project technical blueprint).
- Canonical implementation files:
  - `/Users/ronaldchapman/Desktop/Acquittify/acquittify/ontology/extractor.py`
  - `/Users/ronaldchapman/Desktop/Acquittify/acquittify/ontology/prompts.py`
  - `/Users/ronaldchapman/Desktop/Acquittify/acquittify/ontology/authority_extract.py`
  - `/Users/ronaldchapman/Desktop/Acquittify/scripts/compile_precedent_ontology.py`
  - `/Users/ronaldchapman/Desktop/Acquittify/scripts/caselaw_db_graph.py`
- Governing interpretation-edge contract:
  - Extract and persist edges for: `Case -> Constitutional Amendment`, `Case -> Statute (U.S.C.)`, `Case -> Regulation (C.F.R.)`, `Case -> Federal Rule`, `Case -> Prior Case`.
  - Accept strict extraction payloads with either:
    - `{"holdings": [...], "issues": [...], "relations": [...], "interpretive_edges": [...]}`
    - `{"edges": [...]}` (alias for interpretive edges only).
  - Only create interpretive edges when the deciding court itself makes the interpretive move (not a background quotation).
  - Use normalized edge labels only:
    - Constitutional: `EXTENDS_AMENDMENT`, `NARROWS_AMENDMENT`, `BROADENS_AMENDMENT`, `APPLIES_AMENDMENT`, `EXPLAINS_AMENDMENT`, `CLARIFIES_DOCTRINE`, `INVALIDATES_STATUTE_UNDER`, `INVALIDATES_REGULATION_UNDER`, `UPHOLDS_STATUTE_AGAINST`, `REJECTS_CONSTITUTIONAL_CHALLENGE`, `RECOGNIZES_RIGHT_UNDER`, `LIMITS_AMENDMENT_SCOPE`, `QUESTIONS_PRECEDENT_UNDER`, `OVERRULES_PRECEDENT_UNDER`.
    - Statutory: `INTERPRETS_STATUTE`, `BROADENS_STATUTE`, `NARROWS_STATUTE`, `APPLIES_PLAIN_MEANING`, `USES_LEGISLATIVE_HISTORY`, `APPLIES_LENITY`, `APPLIES_CONSTITUTIONAL_AVOIDANCE`, `FINDS_STATUTE_AMBIGUOUS`, `RESOLVES_STATUTORY_AMBIGUITY`, `INVALIDATES_STATUTE`, `SEVERS_PROVISION`, `DISTINGUISHES_STATUTE`, `EXTENDS_STATUTE`, `REJECTS_EXPANSIVE_READING`, `CONSTRUES_TO_AVOID_CONSTITUTIONAL_ISSUE`.
  - Authority types are normalized to: `CONSTITUTION`, `STATUTE`, `REGULATION`, `FEDERAL_RULE`, `PRIOR_CASE`.
- Governing normalization rules:
  - Constitutional cites normalize to canonical forms such as `U.S. Const. amend. IV` and `U.S. Const. art. I, § 8, cl. 3`.
  - Statutory cites normalize to full form such as `18 U.S.C. § 922(g)(1)`.
  - Rule cites normalize to forms such as `Fed. R. Crim. P. 29`.
  - Prior case references resolve to canonical local `case_id` when possible; unresolved items are queued as `interpretive_edge_unresolved`.
- Governing graph-link strength policy:
  - Shared constitutional links are first-class and strongest ontology links.
  - `shared_constitution` edges are emitted separately from non-constitutional `shared_authority` edges.
  - UI renders `shared_constitution` with highest visual weight and dedicated color.
- Governing compile and persistence behavior:
  - Interpretive edges are persisted on case nodes as `interpretive_edges`.
  - Interpretive authority targets are materialized into source nodes under `/sources`.
  - Interpretive edge outcomes contribute to interpretation event logs in `/events/interpretations`.
  - Determinism/idempotency remains required: same inputs produce no structural drift.
- Governing verification commands:
  - `cd /Users/ronaldchapman/Desktop/Acquittify && PYTHONPATH=. pytest -q tests/ontology`

## Implemented outputs

- Case notes: `cases/scotus|circuits|districts`
- Holding notes: `holdings/`
- Issue notes: `issues/taxonomy/`
- Source notes: `sources/constitution|statutes|regs|secondary`
- Relation notes: `relations/`
- Interpretation events: `events/interpretations/`
- Indices:
  - `indices/issue_index.json`
  - `indices/unresolved_queue.md`
  - `indices/review_checklist.md`
  - `indices/params.yaml`
  - `indices/metrics.yaml`

## Compiler entrypoint

`/Users/ronaldchapman/Desktop/Acquittify/scripts/compile_precedent_ontology.py`

## Doctrine smoke harness

Runner:
`/Users/ronaldchapman/Desktop/Acquittify/scripts/run_ontology_doctrine_smoketest.py`

Example:

```bash
cd /Users/ronaldchapman/Desktop/Acquittify
PYTHONPATH=. python3 scripts/run_ontology_doctrine_smoketest.py \
  --vault-root /tmp/ontology_smoke_vault \
  --work-dir /tmp/ontology_smoke_work \
  --output /tmp/ontology_smoke_report.json
```

## SCOTUS CSV batch compile

Runner:
`/Users/ronaldchapman/Desktop/Acquittify/scripts/compile_scotus_ontology_from_csv.py`

Example (merits-only pilot):

```bash
cd /Users/ronaldchapman/Desktop/Acquittify
PYTHONPATH=. python3 scripts/compile_scotus_ontology_from_csv.py \
  --csv-path "/Users/ronaldchapman/Library/Mobile Documents/iCloud~md~obsidian/Documents/Supreme Court/Ontology/supreme_court_case_file_links.csv" \
  --ontology-vault-root "/Users/ronaldchapman/Library/Mobile Documents/iCloud~md~obsidian/Documents/Supreme Court/Ontology/precedent_vault" \
  --work-dir "/Users/ronaldchapman/Library/Mobile Documents/iCloud~md~obsidian/Documents/Supreme Court/Ontology/.ontology_compile_work" \
  --report-path "/Users/ronaldchapman/Library/Mobile Documents/iCloud~md~obsidian/Documents/Supreme Court/Ontology/ontology_compile_summary.latest.json" \
  --skip-resolver \
  --limit 10 \
  --per-case-timeout 240
```

The runner filters out order-list style entries by default and writes a run summary JSON.

### Modes

1. `--extraction-json <file>`
Use a prepared strict extraction payload.

2. `--run-extractor`
Run local LLM extraction (Ollama) with strict schema validation.

## Example run

```bash
cd /Users/ronaldchapman/Desktop/Acquittify
PYTHONPATH=. python3 scripts/compile_precedent_ontology.py \
  --text-file /tmp/opinion.txt \
  --extraction-json /tmp/extract.json \
  --skip-resolver \
  --vault-root /tmp/precedent_vault \
  --title "Carroll v. United States" \
  --court SCOTUS \
  --court-level supreme \
  --jurisdiction US \
  --date-decided 1925-03-02 \
  --primary-citation "267 U.S. 132" \
  --output /tmp/compile_run.json
```

## Metrics

`metrics.py` computes:

- `PF_holding` (stored in each holding `metrics.PF_holding`)
- `PF_issue` (stored in each issue `metrics.PF_issue`)
- `consensus` and `drift` per issue
- explainability payloads for holdings/issues (source and relation deltas) and interpretation events

Coefficients are controlled by `indices/params.yaml`.

Compile output JSON includes:
- `metrics_summary`
- `metrics_explainability`
- `unresolved_items`
- `unresolved_by_severity`

## Determinism and idempotency

The writer is content-addressed (`write_if_changed`). Re-running with the same input should produce `changed_count = 0`.

## Test suite

```bash
cd /Users/ronaldchapman/Desktop/Acquittify
PYTHONPATH=. pytest -q tests/ontology
```

Includes:

- schema contract tests
- deterministic ID tests
- citation extraction/resolution/role tests
- canonicalization and relation typing tests
- metrics tests
- end-to-end compile idempotency smoke test
- cross-case relation target smoke test (explicit `target_holding_id`)
- cross-case relation target inference smoke test (citation-anchored, no explicit target id)
- fact-dimension extraction + dimension-first canonicalization smoke test
- source-node compilation and secondary-weight impact smoke test
- full doctrine smoke harness (Carroll -> Ross -> Acevedo + circuit split + acceptance checks A-E)
