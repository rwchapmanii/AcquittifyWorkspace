# Minimum Viable Gold Evaluation Set (Design)

Version: 1.0
Status: Draft (Blocking)
Owner: Legal Systems Engineering
Effective Date: 2026-01-28

## 1) Purpose
Define the minimum viable gold evaluation set used for:
- intent calibration
- derive_worker validation
- taxonomy coverage checks
- long-term regression testing

This design specifies scope, metadata, annotations, and storage. It does not populate opinion content.

---

## 2) Scope (Strict Requirements)

### 2.1 Minimum Size
- At least 40 opinions (target 40–60 for coverage stability).

### 2.2 Nationwide Coverage
- At least 8 circuits represented.
- At least 6 district court opinions.
- At least 2 SCOTUS opinions.

### 2.3 Taxonomy Coverage Targets
Each domain must be covered by at least 3 opinions. Opinions may satisfy multiple domains.

- Fourth Amendment
- Fifth Amendment
- Sixth Amendment
- Discovery / Brady / Giglio
- Federal Rules of Evidence (include 404(b), 403, expert evidence)
- Trial management / jury issues
- Appellate issues (sufficiency, preservation, harmless error)
- Sentencing guidelines (calculations, adjustments, reasonableness)
- Post-conviction (§2255 / §3582)
- Substantive criminal law (elements, mens rea, statute-specific defenses)

### 2.4 Composition Targets (Recommended)
- 2–3 opinions per circuit for broad dispersion.
- 1–2 district court opinions per circuit represented.
- Mix of published and unpublished opinions.
- Mix of defense-favorable, neutral, and adverse dispositions.

---

## 3) Required Gold Annotations Per Opinion
Each opinion entry MUST include the following gold labels:

- opinion_id (CourtListener opinion ID)
- court_id
- decision_date
- circuit (if applicable)
- taxonomy_version
- expected_units_total (integer)
- expected_units_tolerance_pct (e.g., 10%)
- expected_holdings_count (integer)
- holdings_tolerance (integer, e.g., ±2)
- primary_taxonomy_codes (list)
- secondary_taxonomy_codes (list)
- favorability_distribution:
  - percent_defense_favorable
  - percent_neutral
  - percent_adverse
- adverse_authority_flags (list of unit identifiers or issue tags)
- circuit_split_indicator:
  - flag (boolean)
  - note (string)
- reviewer_notes (string)

---

## 4) Storage & Review Format

### 4.1 File Format
- JSON (validated by schema).

### 4.2 Directory Layout
- gold/
  - schema/
    - gold_set.schema.json
  - opinions/
    - <opinion_id>.json
  - review_logs/
    - <opinion_id>.disagreements.json
  - index.json

### 4.3 Linkage Requirements
- opinion_id MUST map to CourtListener opinion ID.
- Each unit reference in annotations MUST include raw_opinion_id and excerpt offsets (start/end) when applicable.
- Each opinion JSON must include taxonomy_version to support future re-evaluation.

### 4.4 Review Workflow
- Two independent reviewers required per opinion.
- Disagreements logged in review_logs/<opinion_id>.disagreements.json with:
  - reviewer_id
  - issue_type
  - proposed_change
  - rationale
  - resolution
  - timestamp

### 4.5 Re-evaluation on Taxonomy Changes
- When taxonomy version changes, re-run gold review for affected opinions.
- Record a new review log entry with a cross-reference to the prior version.

---

## 5) Minimum Schema (Design Outline)

Required fields for gold/schema/gold_set.schema.json:
- opinion_id: integer
- court_id: string
- decision_date: date
- circuit: string | null
- taxonomy_version: string
- expected_units_total: integer
- expected_units_tolerance_pct: number
- expected_holdings_count: integer
- holdings_tolerance: integer
- primary_taxonomy_codes: array[string]
- secondary_taxonomy_codes: array[string]
- favorability_distribution: { defense: number, neutral: number, adverse: number }
- adverse_authority_flags: array[string]
- circuit_split_indicator: { flag: boolean, note: string }
- reviewer_notes: string

---

## 6) Selection Strategy (Design Only)
- Start with a coverage matrix by taxonomy domain and circuit.
- Select candidate opinions with diverse outcomes and procedural postures.
- Ensure at least one example per domain includes a HOLDING unit and at least one includes dicta.

---

## 7) Compliance
- This design is blocking for derive_worker go-live.
- No pilot chunking until schema and index.json exist with placeholders for at least 40 opinions.
