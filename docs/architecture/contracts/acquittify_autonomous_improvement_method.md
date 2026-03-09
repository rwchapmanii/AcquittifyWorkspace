# Autonomous Testing and Ontology Improvement for Acquittify

## Objective

Build Acquittify as a **closed-loop legal knowledge system** that can:
1. ingest new case law nightly,
2. extract structured case YAML,
3. validate the extraction and graph against ontology requirements,
4. predict outcomes and retrieve controlling precedent using only time-valid prior law,
5. detect systematic ontology failures,
6. propose bounded ontology changes,
7. replay affected cases in shadow mode, and
8. promote only those changes that improve benchmarks without causing regressions.

The design principle is:

**LLM proposes; symbolic tests decide; production only sees promoted ontology versions.**

---

## Non-negotiable constraints

### 1. Time-locked evaluation
A case may only use authorities available before its decision date. All training, retrieval, graph traversal, and feature generation must be time-sliced to avoid leakage.

### 2. Test-driven ontology engineering
The ontology is not “correct” because it looks elegant. It is correct if it passes:
- shape and typing validation,
- competency-question tests,
- retrieval and treatment tests,
- prediction backtests,
- robustness checks,
- drift checks.

### 3. Autonomous, but not unconstrained
Acquittify may auto-promote **safe ontology deltas** only. High-risk semantic edits must be staged or routed to human review.

### 4. Every ontology change is a versioned experiment
No in-place mutation. Each change produces a new `OntologyVersion` derived from a parent version.

---

## What to test

Use a seven-layer test pyramid.

### Layer 1: extraction and schema tests
Purpose: ensure the raw nightly extraction is structurally valid.

Checks:
- Pydantic validation passes.
- Required fields exist for each node type.
- Citation normalization is valid.
- No null ids on graphable entities.
- No duplicate ids within batch.
- Opinion segmentation exists: facts, procedural posture, issues, reasoning, holding, dicta.
- Date ordering is sane.

Failure action:
- reject case batch,
- quarantine bad records,
- do not generate ontology proposals from invalid records.

### Layer 2: ontology shape tests
Purpose: ensure graph instances conform to ontological expectations.

Checks:
- no orphan `Holding`, `Issue`, `Provision`, or `Outcome` nodes,
- edge domain/range correctness,
- no illegal cardinalities,
- prohibited cycles absent where required,
- ontology namespace/version references present.

Implementation note:
- treat this as a SHACL-style validation layer even if the production graph is Neo4j.
- compile shape constraints into executable graph tests.

### Layer 3: competency-question tests
Purpose: ensure the ontology can answer legally meaningful questions.

Each CQ is stored as:
- natural-language question,
- graph query template,
- expected answer form,
- gold answer set or scoring rule,
- doctrine/jurisdiction tags,
- severity.

Examples:
- Which Sixth Circuit cases distinguish *Miranda* on custodial-interrogation facts?
- Which Supreme Court holdings currently control municipal liability under § 1983?
- Which opinions overruled or limited precedent interpreting a given provision?
- Which cases applying strict scrutiny reversed the lower court?

A CQ fails if the query cannot be answered, returns the wrong answer type, or misses required gold answers beyond threshold.

### Layer 4: retrieval and treatment tests
Purpose: ensure Acquittify finds and labels useful precedent.

Tasks:
- top-k precedent retrieval,
- passage retrieval for controlling language,
- citation treatment classification,
- holding-to-holding linkage.

Key metrics:
- Recall@k,
- MRR,
- nDCG,
- treatment F1,
- holding-link precision.

### Layer 5: predictive backtests
Purpose: test whether recursive case analysis predicts outcomes without leakage.

Tasks:
- disposition,
- winner,
- remedy,
- issue-specific holding,
- direction of decision,
- precedential effect (clarify/limit/overrule).

Backtest design:
- rolling-origin monthly or quarterly evaluation,
- only prior law available at each prediction point,
- evaluate by doctrine, court, jurisdiction, and judge slices.

Metrics:
- macro F1,
- AUROC where applicable,
- Brier score,
- ECE / calibration,
- abstention quality,
- slice-level lift over baseline.

### Layer 6: robustness tests
Purpose: ensure the system is not brittle or using improper signals.

Checks:
- paraphrase stability for fact summaries,
- invariance to irrelevant metadata,
- expected sensitivity to changed controlling precedent,
- expected sensitivity to changed standard of review,
- outcome stability under harmless wording changes.

Use challenge cases:
- multi-issue opinions,
- dicta-heavy opinions,
- fractured decisions,
- overrulings,
- circuit splits,
- mixed procedural outcomes.

### Layer 7: drift and ontology-fitness tests
Purpose: detect where the current ontology is no longer adequate.

Signals:
- rising unknown-term rate,
- rising orphan-rate,
- falling CQ pass rate,
- growing error clusters in one doctrine,
- new citation-treatment confusions,
- novel fact clusters with low nearest-neighbor agreement,
- community split in doctrine graph,
- calibration degradation in recent cohorts.

---

## Data needed for autonomous improvement

Maintain five benchmark sets.

### 1. Gold set
Human-labeled cases with:
- issues,
- provisions,
- holding spans,
- dicta spans,
- treatment edges,
- outcomes,
- doctrine labels.

Use this for high-trust evaluation and release gates.

### 2. Silver set
High-confidence labels from structured sources or repeated agreement across extraction runs.

Use this for broader nightly coverage.

### 3. Challenge set
Curated hard cases:
- overrulings,
- splits,
- en banc reversals,
- multi-opinion cases,
- sparse-fact cases,
- opinions with buried holdings.

### 4. Perturbation set
Synthetic or edited variants used only for robustness checks.

### 5. Shadow recent set
Most recent cases withheld from model tuning, used to estimate current drift and deployment performance.

---

## The autonomous improvement loop

### Nightly phase A: ingest and extract
1. Ingest new opinions and metadata.
2. Extract structured YAML using the current ontology version.
3. Validate with Pydantic and shape constraints.
4. Upsert graph nodes and relationships.
5. Build time-valid feature materializations.

### Nightly phase B: evaluate
6. Run extraction metrics on gold and silver samples.
7. Run CQ suite.
8. Run retrieval/treatment benchmarks.
9. Run rolling-origin backtests on relevant slices.
10. Compute calibration and abstention metrics.
11. Run drift detection.

### Nightly phase C: diagnose
12. Cluster failures by doctrine, court, provision, treatment type, and fact pattern.
13. Convert each error cluster into a machine-readable `FailureSignature`.
14. Identify whether the problem is due to:
    - missing alias,
    - missing leaf concept,
    - bad taxonomy placement,
    - missing edge type,
    - concept split needed,
    - concept merge needed,
    - prompt/extractor weakness,
    - training data gap,
    - prediction model error rather than ontology error.

### Nightly phase D: propose ontology deltas
15. Generate candidate ontology changes from failure signatures.
16. Normalize proposals into a constrained change vocabulary.
17. Score each proposal.
18. Reject proposals that violate hard safety rules.
19. Apply surviving proposals to a **shadow ontology branch**.

### Nightly phase E: replay and compare
20. Re-extract only affected cases plus evaluation slices.
21. Rebuild impacted subgraph.
22. Re-run all benchmark layers.
23. Compare child ontology version to parent.
24. Promote, stage, or reject.

### Nightly phase F: record and learn
25. Persist all proposals, scores, decisions, and metrics.
26. Feed accepted and rejected proposals back into the proposal ranker.
27. Update failure-prioritization queues for the next night.

---

## Constrained ontology change vocabulary

Every autonomous proposal must be one of these types.

### Auto-promotable candidates
Safe when thresholds are met.

- `ADD_ALIAS`
- `ADD_LEAF_TOPIC`
- `ADD_LEAF_ISSUE`
- `ADD_PROVISION_ALIAS`
- `ADD_DOCTRINE_MEMBERSHIP`
- `ADD_EDGE_INSTANCE`
- `REWEIGHT_EDGE_SCORING`
- `REFINE_EXTRACTION_PROMPT`
- `ADD_CQ`

### Shadow-only candidates
Require replay plus an expanded benchmark.

- `SPLIT_CONCEPT`
- `MERGE_CONCEPT`
- `REPARENT_NODE`
- `ADD_RELATION_TYPE`
- `CHANGE_RELATION_CARDINALITY`
- `CHANGE_HOLDING_SEGMENTATION_RULE`
- `CHANGE_DOCTRINE_CLUSTERING_RULE`

### Human-review candidates
Never auto-promote.

- `ADD_TOP_LEVEL_CLASS`
- `REMOVE_CLASS`
- `REMOVE_RELATION_TYPE`
- `DESTRUCTIVE_MERGE`
- `MAJOR_REPARENTING`
- `SEMANTICS_CHANGE_TO_BINDING_STATUS`
- `CHANGE_PRECEDENT_WEIGHTING_POLICY`

---

## Proposal generation rules

Use a hybrid of symbolic discovery and LLM synthesis.

### Symbolic proposal triggers
1. **Unknown phrase cluster**
   - repeated unseen phrases map near an existing concept,
   - propose alias or new leaf concept.

2. **Confusion matrix hotspot**
   - e.g. `DISTINGUISHES` vs `LIMITS`,
   - propose edge-taxonomy refinement or better decision rule.

3. **CQ failure hotspot**
   - repeated failure to answer a question form,
   - propose missing relation or missing property.

4. **Graph anomaly**
   - orphan nodes, collapsed super-nodes, disconnected doctrine components,
   - propose structural repair.

5. **Outcome residual cluster**
   - prediction errors concentrated in a doctrine or court,
   - propose ontology refinement before model tuning.

### LLM proposal generation
The LLM may only emit proposals in a strict JSON schema:
- `change_type`
- `target_entities`
- `rationale`
- `evidence_case_ids`
- `expected_effect`
- `risk_level`
- `migration_steps`

The LLM does **not** change production ontology directly.

---

## Proposal scoring

Score each candidate change using a bounded utility function.

```text
proposal_score =
  0.25 * coverage_lift
+ 0.20 * cq_lift
+ 0.20 * retrieval_lift
+ 0.15 * prediction_lift
+ 0.10 * consistency_lift
+ 0.10 * drift_reduction
- 0.15 * complexity_penalty
- 0.20 * regression_penalty
- 0.25 * semantic_risk
```

Where:
- `coverage_lift` = decrease in unknown/unmapped spans,
- `cq_lift` = increase in CQ pass rate,
- `retrieval_lift` = gain in precedent retrieval/treatment metrics,
- `prediction_lift` = improvement in forward backtests,
- `consistency_lift` = reduction in shape or contradiction errors,
- `drift_reduction` = improvement on recent-shadow slices,
- `complexity_penalty` = ontology bloat cost,
- `regression_penalty` = any performance harm elsewhere,
- `semantic_risk` = risk from changing legal meaning rather than coverage.

Hard vetoes override score.

---

## Promotion policy

### Hard vetoes
Reject automatically if any of these occur:
- shape pass rate drops below 100% on gold or benchmark slices,
- CQ pass rate decreases on critical CQs,
- retrieval/treatment quality regresses beyond tolerance,
- calibration worsens beyond tolerance on protected slices,
- new destructive ontology change without human approval,
- temporal leakage detected,
- conflict with frozen ontology invariants.

### Auto-promote lane
Promote if all are true:
- safe change type,
- proposal confidence above threshold,
- evidence support above threshold,
- no hard veto,
- parent-to-child benchmark deltas non-negative except within tiny tolerance,
- at least one of coverage, CQ, retrieval, or prediction improves materially.

### Shadow lane
Keep in shadow if:
- promising but uncertain,
- benefits one doctrine while risking another,
- concept split/merge is underdetermined,
- evidence size too small.

### Human lane
Require review if:
- semantic consequences are substantial,
- taxonomy changes affect broad slices,
- proposal changes legal meaning rather than representation,
- proposal touches binding/nonbinding semantics.

---

## Ontology-fitness metrics

Track these every night.

### Structural metrics
- `shape_pass_rate`
- `orphan_node_rate`
- `edge_domain_range_error_rate`
- `duplicate_entity_rate`
- `merge_collision_rate`

### Coverage metrics
- `issue_mapping_coverage`
- `provision_mapping_coverage`
- `doctrine_mapping_coverage`
- `unknown_phrase_rate`
- `alias_hit_rate`

### Query metrics
- `cq_pass_rate`
- `cq_partial_credit`
- `cq_latency`

### Retrieval and reasoning metrics
- `precedent_recall_at_5`
- `precedent_recall_at_20`
- `passage_recall_at_20`
- `treatment_macro_f1`
- `holding_link_precision`

### Prediction metrics
- `disposition_macro_f1`
- `winner_macro_f1`
- `remedy_macro_f1`
- `direction_macro_f1`
- `brier_score`
- `ece`
- `abstention_auc`

### Drift metrics
- `recent_vs_historical_error_gap`
- `unknown_term_growth`
- `doctrine_cluster_instability`
- `calibration_drift`
- `citation_pattern_shift`

---

## Competency questions as executable tests

Treat CQs like unit tests for the ontology.

Each CQ should include:
- `cq_id`
- `question_text`
- `doctrine_tags`
- `jurisdiction_tags`
- `severity`
- `query_template`
- `expected_answer_type`
- `gold_answer_ids`
- `scoring_method`
- `time_validity_rule`

Recommended CQ families:
1. controlling precedent
2. treatment and overruling
3. issue/provision linkage
4. procedural posture and standard of review
5. remedy availability
6. doctrine membership
7. holding vs dicta discrimination

---

## Recursive prediction architecture

The ontology loop must feed the predictor.

### Principle
Prediction should use:
- facts,
- issues,
- provisions,
- holdings,
- doctrine state,
- citation treatment graph,
- time-valid precedent subgraph.

### Recommended cycle
1. Build a target-case representation.
2. Retrieve a time-valid precedent subgraph.
3. Aggregate influence through typed edges.
4. Predict outcomes.
5. Store errors.
6. Ask whether the error is due to missing ontology capacity.
7. If yes, create a bounded ontology proposal.
8. Re-evaluate under a child ontology version.

This creates a **recursive error-correction loop**:

```text
prediction error
  -> failure signature
  -> ontology proposal
  -> shadow replay
  -> benchmark comparison
  -> ontology promotion or rejection
  -> improved future prediction
```

---

## Distinguishing model errors from ontology errors

Not every prediction miss is an ontology problem.

Classify misses this way:

### Ontology error likely
- unknown legal issue phrase,
- repeated CQ failure for the same relation,
- holding exists but cannot be represented,
- graph structure cannot express the case treatment,
- same fact pattern repeatedly maps to mixed or null ontology classes.

### Model error likely
- ontology coverage is high,
- CQs pass,
- retrieval finds correct precedent,
- but prediction is still wrong.

### Data error likely
- source text corrupted,
- bad citation normalization,
- missing opinion segment,
- duplicate or stale case metadata.

Only ontology-likely misses should drive ontology evolution.

---

## Safe autonomous scope

Acquittify should be autonomous in:
- alias expansion,
- leaf taxonomy growth,
- adding executable tests,
- score reweighting,
- extractor prompt refinement,
- doctrine membership suggestions,
- edge instance creation from explicit evidence.

Acquittify should not be fully autonomous in:
- changing the meaning of legal concepts,
- redefining holding vs dicta policy,
- changing binding-force semantics,
- major hierarchy rewrites,
- deleting ontology branches.

---

## Graph objects to add for governance

Add these node labels to the operational graph:
- `OntologyVersion`
- `OntologyChangeProposal`
- `EvaluationRun`
- `BenchmarkDataset`
- `CompetencyQuestion`
- `MetricSnapshot`
- `FailureSignature`
- `ErrorCluster`
- `DriftSignal`

Add relationships such as:
- `(:OntologyChangeProposal)-[:PROPOSES_VERSION]->(:OntologyVersion)`
- `(:OntologyChangeProposal)-[:DERIVED_FROM]->(:FailureSignature)`
- `(:EvaluationRun)-[:EVALUATES]->(:OntologyVersion)`
- `(:EvaluationRun)-[:USES_DATASET]->(:BenchmarkDataset)`
- `(:EvaluationRun)-[:MEASURED]->(:MetricSnapshot)`
- `(:CompetencyQuestion)-[:TESTS]->(:Doctrine)`
- `(:ErrorCluster)-[:SUGGESTS]->(:OntologyChangeProposal)`
- `(:DriftSignal)-[:TRIGGERED_REVIEW_OF]->(:OntologyVersion)`

---

## Release gates

A child ontology version may replace the current production version only if:
- all hard invariants pass,
- no critical CQ regresses,
- no doctrine slice degrades beyond tolerance,
- no recent-shadow slice degrades beyond tolerance,
- calibration is stable or improved,
- proposal type is in the allowed lane,
- rollback package is generated.

---

## Rollback strategy

Every promotion must store:
- parent version,
- migration diff,
- affected case ids,
- impacted doctrine slices,
- metric deltas,
- rollback script.

If any post-promotion canary metric breaches threshold:
- revert to parent ontology version,
- mark proposal family as high-risk,
- widen human review for similar proposals.

---

## Practical rollout plan

### Phase 1
Implement validation, CQ framework, benchmark registry, and shadow ontology versions.

### Phase 2
Implement failure signatures, proposal schema, and safe auto-promote lane for aliases and leaf topics.

### Phase 3
Implement shadow replay for concept splits/merges and doctrine clustering changes.

### Phase 4
Train a proposal ranker using the history of accepted/rejected changes.

### Phase 5
Expand doctrine-specific benchmark suites and move toward continuous ontology optimization.

---

## Recommended acceptance rule for v1

For the first production version, keep it strict:
- only `ADD_ALIAS`, `ADD_LEAF_TOPIC`, `ADD_LEAF_ISSUE`, `ADD_PROVISION_ALIAS`, `ADD_EDGE_INSTANCE`, and `ADD_CQ` may auto-promote,
- everything else is shadow or human review,
- use a monthly audit of all promoted ontology deltas.

That gives Acquittify a realistic path to autonomous improvement without letting it silently rewrite the meaning of the law.
