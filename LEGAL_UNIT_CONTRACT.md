# LEGAL UNIT CONTRACT

Version: 1.0
Status: Draft (Blocking)
Owner: Legal Systems Engineering
Effective Date: 2026-01-28
Applies To: derive_worker v1 and any downstream reranking/audit logic that consumes derived.legal_unit

## 0) Purpose
This contract defines deterministic, enforceable rules for converting judicial text into derived.legal_unit records. The rules are designed for defense practice, auditability, and long-term regression stability.

## 1) Global Requirements (All Unit Types)

### 1.1 Minimum Text Integrity
- Unit text MUST be a contiguous excerpt from a single opinion.
- Unit text MUST be human-readable (no encoding artifacts, not empty, not pure citation list).
- Unit text MUST preserve original sentence order.

### 1.2 Duplicate Prevention
- Two units within the same opinion MUST NOT be materially identical (>=90% token overlap).
- If overlap exceeds 90%, keep the unit with narrower scope.

### 1.3 Scope Control
- Each unit MUST address a single legal proposition, fact pattern, procedural event, or disposition outcome.
- If a paragraph contains multiple propositions, split into multiple units unless prohibited by type rules.

### 1.4 Citation Handling
- Citations are preserved if present.
- If a unit requires citations (see type rules), it MUST contain at least one formal case citation or explicit reference to a controlling authority.

### 1.5 Defense Orientation
- Units are extracted without editorialization.
- Favorability scoring is applied after extraction and does not change unit boundaries.

---

## 2) Legal Unit Types (Hard Rules)

Each unit_type below includes mandatory inclusion/exclusion rules, scope bounds, citation requirements, and downstream use.

### 2.1 FACT_PATTERN
**Definition:** Material facts that establish the relevant conduct, actors, timing, locations, and investigatory steps.

**Inclusion Rules (ALL REQUIRED):**
- Describes objective events (searches, seizures, statements, arrests, trials, motions, hearings, sentencing facts).
- Contains at least one concrete fact (who/what/when/where/how) tied to legal analysis in the opinion.

**Exclusion Rules:**
- Exclude legal conclusions, standards, or outcome statements.
- Exclude procedural rulings unless the text solely describes procedural history without legal analysis.

**Maximum Logical Scope:**
- A single coherent factual episode or phase (e.g., stop, interrogation, suppression hearing). No multi-episode aggregation.

**Citation Required:**
- Not required.

**Facts/Law Allowed:**
- Facts only (no legal standards).

**Downstream Use:**
- Retrieval (fact pattern matching), audit context, reasoning support.

---

### 2.2 LEGAL_STANDARD
**Definition:** A statement of a governing rule, test, or legal standard that guides the analysis.

**Inclusion Rules (ALL REQUIRED):**
- Expresses a legal test, standard, or rule (e.g., reasonableness, probable cause, harmless error).
- Is framed as a general rule applicable beyond the case-specific facts.

**Exclusion Rules:**
- Exclude application to case facts (belongs in APPLICATION).
- Exclude pure holdings unless it primarily states the rule rather than its application.

**Maximum Logical Scope:**
- One rule/test with associated elements or factors; may include short definitional sentences.

**Citation Required:**
- Required. Must cite at least one authority or contain an explicit statement that it is binding precedent.

**Facts/Law Allowed:**
- Law only (no case-specific facts).

**Downstream Use:**
- Reasoning and calibration; retrieval for standards.

---

### 2.3 APPLICATION
**Definition:** The court’s application of a legal standard to the case-specific facts.

**Inclusion Rules (ALL REQUIRED):**
- Connects a legal standard to a case fact or set of facts.
- Contains evaluative language (e.g., “therefore,” “because,” “we find”) applying rule to facts.

**Exclusion Rules:**
- Exclude bare standard statements (LEGAL_STANDARD).
- Exclude procedural history or outcome-only statements (PROCEDURAL or DISPOSITION).

**Maximum Logical Scope:**
- One standard applied to one fact pattern (can include short chain of reasoning).

**Citation Required:**
- Optional.

**Facts/Law Allowed:**
- Both facts and law.

**Downstream Use:**
- Primary reasoning unit for argument synthesis; retrieval for analogous fact-application pairs.

---

### 2.4 HOLDING
**Definition:** A dispositive legal conclusion resolving a legal issue that is necessary to the judgment.

**Inclusion Rules (ALL REQUIRED):**
- States the court’s resolution of a legal question.
- The resolution is necessary to the disposition.
- The statement can be traced to an issue that, if decided otherwise, would alter the outcome.

**Exclusion Rules:**
- Exclude advisory statements, hypotheticals, or alternative reasoning not required to reach the outcome.
- Exclude policy commentary.

**Maximum Logical Scope:**
- One legal issue resolution per unit.

**Citation Required:**
- Not required, but preferred.

**Facts/Law Allowed:**
- Primarily law; minimal facts only as needed to define the issue context.

**Downstream Use:**
- Authoritative reasoning, audit trail, and binding/nonbinding weight.

---

### 2.5 PROCEDURAL
**Definition:** Procedural posture, jurisdiction, standard of review, and litigation events that frame the court’s authority or scope of review.

**Inclusion Rules (ALL REQUIRED):**
- Describes procedural posture, jurisdiction, standard of review, or procedural history that affects review.

**Exclusion Rules:**
- Exclude substantive legal standards (LEGAL_STANDARD).
- Exclude merits outcomes (DISPOSITION).

**Maximum Logical Scope:**
- One procedural topic (e.g., standard of review for suppression ruling).

**Citation Required:**
- Optional.

**Facts/Law Allowed:**
- Law or procedural facts (not substantive facts).

**Downstream Use:**
- Audit and litigation strategy context (e.g., preservation, standards of review).

---

### 2.6 DISPOSITION
**Definition:** The final outcome of claims, convictions, sentences, or motions.

**Inclusion Rules (ALL REQUIRED):**
- States outcome (affirmed, reversed, vacated, remanded, dismissed, granted, denied).

**Exclusion Rules:**
- Exclude reasoning; outcome-only statements.
- Exclude holdings that explain why (HOLDING or APPLICATION).

**Maximum Logical Scope:**
- One outcome for a claim or case segment.

**Citation Required:**
- Not required.

**Facts/Law Allowed:**
- Neither; outcome only.

**Downstream Use:**
- Audit trail and outcome mapping; not primary retrieval.

---

## 3) HOLDING vs DICTA Rules (Critical)

### 3.1 HOLDING Qualification
A statement is a HOLDING if and only if ALL are true:
1. It resolves a contested legal question presented for decision.
2. It is necessary to the outcome.
3. It is not framed as hypothetical or alternative unnecessary reasoning.
4. Removing it would change the disposition or required remedy.

### 3.2 Dicta Identification
Mark as dicta when ANY are true:
- The statement addresses an issue not required to resolve the case.
- The statement appears in a “even if” or “assuming arguendo” clause.
- The statement presents a general observation or policy remark.
- The statement addresses a scenario not present in the record.

### 3.3 Partial Holdings
- Partial holdings are allowed ONLY if the unit can be isolated to the necessary portion.
- If a paragraph contains both holding and dicta, split and label separately.
- If splitting would distort meaning or remove necessary qualifiers, mark the entire paragraph as dicta and record an audit note.

### 3.4 Mixed Paragraph Handling
- If mixed content is separable at sentence boundaries, split into HOLDING and APPLICATION or LEGAL_STANDARD.
- If inseparable, assign the stricter label: HOLDING only if every sentence is necessary; otherwise dicta and reclassify as APPLICATION or LEGAL_STANDARD with dicta flag.

### 3.5 Disposition Tie Requirement
- A HOLDING must tie directly to the disposition. If no direct tie, it is dicta.

---

## 4) Favorability Scale (Defense-Relative)

### 4.1 Numeric Range
- Scale: -100 to +100

### 4.2 Anchors
- +100: Strongly defense-favorable holding; directly supports suppression, reversal, dismissal, or reduced sentence under common facts.
- +50: Moderately defense-favorable; clarifies a standard or limits government authority but may be distinguishable.
- 0: Neutral or purely procedural; no clear defense advantage.
- -50: Moderately adverse; upholds government action but sets limits or leaves defense arguments open.
- -100: Strongly adverse; forecloses common defense arguments and endorses expansive government power.

### 4.3 Scoring Rules
- Adverse but distinguishable authority: score between -10 and -40 depending on ease of distinction.
- Mixed rulings: compute issue-level scores; overall unit score is weighted average by legal impact (major issue weight=2x minor).
- Government wins with defense-helpful standards: score between -5 and +30 depending on the restrictiveness of the standard.

---

## 5) Authority Weight Scale (Frozen)

### 5.1 Hierarchy (Higher is more authoritative)
1. SCOTUS holding: 100
2. SCOTUS dicta: 70
3. Circuit en banc published: 90
4. Circuit published panel: 80
5. Circuit unpublished: 55
6. District court published: 45
7. District court unpublished: 35
8. Orders, summary dispositions: 30
9. Per curiam (published): +0 adjustment; Per curiam (unpublished): -5 adjustment

### 5.2 Dicta Penalty
- Dicta penalty: -20 from base authority weight.

### 5.3 Cross-Circuit Use
- Non-controlling circuit authority: -10 adjustment.

### 5.4 Ties and Overrides
- If authority type is unknown, default to 40.
- No ad hoc overrides permitted without contract amendment.

---

## 6) Auditability Requirements

- Each derived.legal_unit MUST be traceable to raw opinion id and a source excerpt.
- Units MUST record: unit_type, favorability, authority_weight, and dicta flag where applicable.
- Reviewers MUST be able to reproduce classification using only this contract.

---

## 7) Change Control

- Any change requires version bump and signed approval from Legal SME and Systems Engineering.
- Contract changes are not retroactive unless re-derivation is approved and logged.
