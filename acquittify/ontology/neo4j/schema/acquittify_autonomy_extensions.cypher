// Acquittify ontology-governance and autonomous-evaluation graph extensions
// Neo4j 5.x schema additions

// -----------------------------------------------------------------------------
// Governance nodes
// -----------------------------------------------------------------------------
CREATE CONSTRAINT ontology_version_id_unique IF NOT EXISTS
FOR (n:OntologyVersion) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT ontology_change_proposal_id_unique IF NOT EXISTS
FOR (n:OntologyChangeProposal) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT evaluation_run_id_unique IF NOT EXISTS
FOR (n:EvaluationRun) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT benchmark_dataset_id_unique IF NOT EXISTS
FOR (n:BenchmarkDataset) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT competency_question_id_unique IF NOT EXISTS
FOR (n:CompetencyQuestion) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT metric_snapshot_id_unique IF NOT EXISTS
FOR (n:MetricSnapshot) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT failure_signature_id_unique IF NOT EXISTS
FOR (n:FailureSignature) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT error_cluster_id_unique IF NOT EXISTS
FOR (n:ErrorCluster) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT drift_signal_id_unique IF NOT EXISTS
FOR (n:DriftSignal) REQUIRE n.id IS UNIQUE;

// -----------------------------------------------------------------------------
// Helpful indexes
// -----------------------------------------------------------------------------
CREATE RANGE INDEX ontology_version_status_idx IF NOT EXISTS
FOR (n:OntologyVersion) ON (n.status);

CREATE RANGE INDEX ontology_version_semver_idx IF NOT EXISTS
FOR (n:OntologyVersion) ON (n.semantic_version);

CREATE RANGE INDEX ontology_change_type_idx IF NOT EXISTS
FOR (n:OntologyChangeProposal) ON (n.change_type);

CREATE RANGE INDEX ontology_change_status_idx IF NOT EXISTS
FOR (n:OntologyChangeProposal) ON (n.status);

CREATE RANGE INDEX ontology_change_lane_idx IF NOT EXISTS
FOR (n:OntologyChangeProposal) ON (n.lane);

CREATE RANGE INDEX ontology_change_risk_idx IF NOT EXISTS
FOR (n:OntologyChangeProposal) ON (n.semantic_risk);

CREATE RANGE INDEX evaluation_run_started_idx IF NOT EXISTS
FOR (n:EvaluationRun) ON (n.started_at);

CREATE RANGE INDEX evaluation_run_status_idx IF NOT EXISTS
FOR (n:EvaluationRun) ON (n.status);

CREATE RANGE INDEX benchmark_dataset_name_idx IF NOT EXISTS
FOR (n:BenchmarkDataset) ON (n.name);

CREATE RANGE INDEX competency_question_severity_idx IF NOT EXISTS
FOR (n:CompetencyQuestion) ON (n.severity);

CREATE RANGE INDEX metric_snapshot_name_idx IF NOT EXISTS
FOR (n:MetricSnapshot) ON (n.metric_name);

CREATE RANGE INDEX failure_signature_type_idx IF NOT EXISTS
FOR (n:FailureSignature) ON (n.signature_type);

CREATE RANGE INDEX drift_signal_type_idx IF NOT EXISTS
FOR (n:DriftSignal) ON (n.signal_type);

CREATE TEXT INDEX competency_question_text_idx IF NOT EXISTS
FOR (n:CompetencyQuestion) ON (n.question_text);

// -----------------------------------------------------------------------------
// Suggested node property conventions
// -----------------------------------------------------------------------------
// :OntologyVersion {
//   id,
//   semantic_version,
//   parent_version_id,
//   status,            // draft|shadow|promoted|rejected|rolled_back
//   created_at,
//   promoted_at,
//   created_by,
//   notes,
//   ontology_hash
// }
//
// :OntologyChangeProposal {
//   id,
//   change_type,
//   lane,              // auto|shadow|human
//   status,            // proposed|accepted|rejected|shadowed|promoted
//   confidence,
//   semantic_risk,
//   evidence_case_count,
//   proposal_score,
//   rationale,
//   migration_json,
//   created_at
// }
//
// :EvaluationRun {
//   id,
//   status,
//   started_at,
//   finished_at,
//   model_version,
//   extractor_version,
//   run_type,          // nightly|shadow_replay|release_gate|canary
//   summary_json
// }
//
// :BenchmarkDataset {
//   id,
//   name,
//   split,             // gold|silver|challenge|perturbation|shadow_recent
//   frozen,
//   version,
//   created_at
// }
//
// :CompetencyQuestion {
//   id,
//   question_text,
//   severity,
//   doctrine_tags_json,
//   jurisdiction_tags_json,
//   query_template,
//   expected_answer_type,
//   time_validity_rule,
//   scoring_method
// }
//
// :MetricSnapshot {
//   id,
//   metric_name,
//   metric_value,
//   split,
//   slice_key,
//   ontology_version_id,
//   evaluation_run_id,
//   measured_at
// }
//
// :FailureSignature {
//   id,
//   signature_type,
//   summary,
//   doctrine_key,
//   jurisdiction_key,
//   support_count,
//   created_at,
//   details_json
// }
//
// :ErrorCluster {
//   id,
//   cluster_type,
//   doctrine_key,
//   count,
//   drift_score,
//   details_json,
//   created_at
// }
//
// :DriftSignal {
//   id,
//   signal_type,
//   severity,
//   observed_value,
//   baseline_value,
//   delta,
//   created_at,
//   details_json
// }

// -----------------------------------------------------------------------------
// Relationship conventions (upserted by application code)
// -----------------------------------------------------------------------------
// (:OntologyVersion)-[:DERIVED_FROM]->(:OntologyVersion)
// (:OntologyChangeProposal)-[:PROPOSES_VERSION]->(:OntologyVersion)
// (:OntologyChangeProposal)-[:DERIVED_FROM]->(:FailureSignature)
// (:OntologyChangeProposal)-[:AFFECTS]->(:Doctrine|:LegalIssue|:RuleStatement|:Holding|:Topic|:LegalProvision)
// (:EvaluationRun)-[:EVALUATES]->(:OntologyVersion)
// (:EvaluationRun)-[:USES_DATASET]->(:BenchmarkDataset)
// (:EvaluationRun)-[:MEASURED]->(:MetricSnapshot)
// (:CompetencyQuestion)-[:TESTS]->(:Doctrine|:LegalIssue|:LegalProvision)
// (:FailureSignature)-[:OBSERVED_IN]->(:Case)
// (:ErrorCluster)-[:CONTAINS]->(:FailureSignature)
// (:ErrorCluster)-[:SUGGESTS]->(:OntologyChangeProposal)
// (:DriftSignal)-[:TRIGGERED_REVIEW_OF]->(:OntologyVersion)
// (:MetricSnapshot)-[:ABOUT]->(:Doctrine|:Court|:Jurisdiction)
