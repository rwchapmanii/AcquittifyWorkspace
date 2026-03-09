# Derive-Worker Readiness Checklist

Version: 1.0
Status: Draft (Blocking)
Effective Date: 2026-01-28

## GO / NO-GO Criteria (Pre-Pilot)

### A) Required Documents and Approvals (GO)
- Legal Unit Contract finalized and approved by Legal SME + Systems Engineering.
- Gold set design approved and committed.
- Gold set schema file exists and passes validation.
- Review protocol defined (two-reviewer rule + disagreement resolution log).

### B) Guardrail Tests (GO)
- Unit inflation rate < 1.5x expected_units_total on a 5-opinion dry run.
- HOLDING classification agreement between two reviewers ≥ 90%.
- Dicta labeling agreement between two reviewers ≥ 90%.
- 0 missing required fields in sample derived.legal_unit outputs:
  - unit_type
  - favorability
  - authority_weight
  - dicta flag (when applicable)
  - raw_opinion_id

### C) Admin UI Readiness (GO)
- Admin UI reachable and authenticated.
- Governance pages render without errors.
- Audit views display legal units and guardrail events.

### D) Gold Set Schema Existence (GO)
- gold/schema/gold_set.schema.json committed.
- gold/index.json exists with at least 40 opinion_id placeholders.

---

## Hard Stop Conditions During Pilot (Immediate Halt)

- >5% of units missing required fields.
- >3% of units labeled HOLDING without direct disposition tie.
- Unit inflation exceeds 2x expected_units_total in any gold comparison.
- derived.ingestion_error_event exceeds 2% of total units in a batch.
- Any loss of traceability (missing raw_opinion_id or excerpt offsets).
- Any single opinion exceeds max_units_per_opinion guardrail.

---

## Exit Criteria (Pilot Completion)

- All guardrail thresholds pass across full pilot batch.
- No unresolved review disagreements in gold set evaluations.
- Favorability distribution aligns with gold tolerances across the batch.
- Authority weight distribution matches expected hierarchy without anomalies.
