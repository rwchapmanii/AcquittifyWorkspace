// Acquittify U.S. Case Law Graph Schema
// Target: Neo4j 5.x
//
// Design notes:
// 1. Every node carries a common `id` property plus its domain-specific id field (case_id, opinion_id, etc.).
//    Constraints use `id` so loader logic can upsert all labels uniformly.
// 2. Every relationship carries a common `edge_id` property. Constraints use `edge_id`.
// 3. Neo4j relationships are stored directionally. For logically symmetric edges
//    (SAME_ISSUE, SAME_PROVISION, SAME_FACT_CLUSTER), persist one canonical edge with
//    endpoints sorted lexicographically and a stable edge_id.
// 4. This DDL normalizes three schema gaps from the conceptual YAML:
//      - Case -> Opinion is persisted as :HAS_OPINION
//      - Case -> Topic is persisted as :HAS_TOPIC
//      - Case -> Motion is persisted as :HAS_MOTION
// 5. Full nested YAML should remain in object storage / document storage.
//    Neo4j stores only flattened graph properties needed for graph traversal and filtering.
//
// ---------------------------------------------------------------------------
// CORE UNIQUENESS CONSTRAINTS (Community + Enterprise)
// ---------------------------------------------------------------------------

CREATE CONSTRAINT case_id_unique IF NOT EXISTS
FOR (n:Case)
REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT opinion_id_unique IF NOT EXISTS
FOR (n:Opinion)
REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT court_id_unique IF NOT EXISTS
FOR (n:Court)
REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT judge_id_unique IF NOT EXISTS
FOR (n:Judge)
REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT party_id_unique IF NOT EXISTS
FOR (n:Party)
REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT legal_issue_id_unique IF NOT EXISTS
FOR (n:LegalIssue)
REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT rule_statement_id_unique IF NOT EXISTS
FOR (n:RuleStatement)
REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT holding_id_unique IF NOT EXISTS
FOR (n:Holding)
REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT dictum_id_unique IF NOT EXISTS
FOR (n:Dictum)
REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT fact_pattern_id_unique IF NOT EXISTS
FOR (n:FactPattern)
REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT legal_provision_id_unique IF NOT EXISTS
FOR (n:LegalProvision)
REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT doctrine_id_unique IF NOT EXISTS
FOR (n:Doctrine)
REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT topic_id_unique IF NOT EXISTS
FOR (n:Topic)
REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT outcome_id_unique IF NOT EXISTS
FOR (n:Outcome)
REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT motion_id_unique IF NOT EXISTS
FOR (n:Motion)
REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT remedy_id_unique IF NOT EXISTS
FOR (n:Remedy)
REQUIRE n.id IS UNIQUE;

// ---------------------------------------------------------------------------
// RELATIONSHIP UNIQUENESS CONSTRAINTS
// Each relationship must include `edge_id`.
// ---------------------------------------------------------------------------

CREATE CONSTRAINT cites_edge_id_unique IF NOT EXISTS
FOR ()-[r:CITES]-()
REQUIRE r.edge_id IS UNIQUE;

CREATE CONSTRAINT cites_case_edge_id_unique IF NOT EXISTS
FOR ()-[r:CITES_CASE]-()
REQUIRE r.edge_id IS UNIQUE;

CREATE CONSTRAINT relies_on_edge_id_unique IF NOT EXISTS
FOR ()-[r:RELIES_ON]-()
REQUIRE r.edge_id IS UNIQUE;

CREATE CONSTRAINT follows_edge_id_unique IF NOT EXISTS
FOR ()-[r:FOLLOWS]-()
REQUIRE r.edge_id IS UNIQUE;

CREATE CONSTRAINT distinguishes_edge_id_unique IF NOT EXISTS
FOR ()-[r:DISTINGUISHES]-()
REQUIRE r.edge_id IS UNIQUE;

CREATE CONSTRAINT overrules_edge_id_unique IF NOT EXISTS
FOR ()-[r:OVERRULES]-()
REQUIRE r.edge_id IS UNIQUE;

CREATE CONSTRAINT limits_edge_id_unique IF NOT EXISTS
FOR ()-[r:LIMITS]-()
REQUIRE r.edge_id IS UNIQUE;

CREATE CONSTRAINT questions_edge_id_unique IF NOT EXISTS
FOR ()-[r:QUESTIONS]-()
REQUIRE r.edge_id IS UNIQUE;

CREATE CONSTRAINT interprets_edge_id_unique IF NOT EXISTS
FOR ()-[r:INTERPRETS]-()
REQUIRE r.edge_id IS UNIQUE;

CREATE CONSTRAINT applies_rule_edge_id_unique IF NOT EXISTS
FOR ()-[r:APPLIES_RULE]-()
REQUIRE r.edge_id IS UNIQUE;

CREATE CONSTRAINT states_holding_edge_id_unique IF NOT EXISTS
FOR ()-[r:STATES_HOLDING]-()
REQUIRE r.edge_id IS UNIQUE;

CREATE CONSTRAINT states_dictum_edge_id_unique IF NOT EXISTS
FOR ()-[r:STATES_DICTUM]-()
REQUIRE r.edge_id IS UNIQUE;

CREATE CONSTRAINT has_issue_edge_id_unique IF NOT EXISTS
FOR ()-[r:HAS_ISSUE]-()
REQUIRE r.edge_id IS UNIQUE;

CREATE CONSTRAINT has_fact_pattern_edge_id_unique IF NOT EXISTS
FOR ()-[r:HAS_FACT_PATTERN]-()
REQUIRE r.edge_id IS UNIQUE;

CREATE CONSTRAINT involves_party_edge_id_unique IF NOT EXISTS
FOR ()-[r:INVOLVES_PARTY]-()
REQUIRE r.edge_id IS UNIQUE;

CREATE CONSTRAINT decided_by_edge_id_unique IF NOT EXISTS
FOR ()-[r:DECIDED_BY]-()
REQUIRE r.edge_id IS UNIQUE;

CREATE CONSTRAINT issued_by_edge_id_unique IF NOT EXISTS
FOR ()-[r:ISSUED_BY]-()
REQUIRE r.edge_id IS UNIQUE;

CREATE CONSTRAINT belongs_to_doctrine_edge_id_unique IF NOT EXISTS
FOR ()-[r:BELONGS_TO_DOCTRINE]-()
REQUIRE r.edge_id IS UNIQUE;

CREATE CONSTRAINT has_topic_edge_id_unique IF NOT EXISTS
FOR ()-[r:HAS_TOPIC]-()
REQUIRE r.edge_id IS UNIQUE;

CREATE CONSTRAINT same_issue_edge_id_unique IF NOT EXISTS
FOR ()-[r:SAME_ISSUE]-()
REQUIRE r.edge_id IS UNIQUE;

CREATE CONSTRAINT same_provision_edge_id_unique IF NOT EXISTS
FOR ()-[r:SAME_PROVISION]-()
REQUIRE r.edge_id IS UNIQUE;

CREATE CONSTRAINT same_fact_cluster_edge_id_unique IF NOT EXISTS
FOR ()-[r:SAME_FACT_CLUSTER]-()
REQUIRE r.edge_id IS UNIQUE;

CREATE CONSTRAINT appeal_from_edge_id_unique IF NOT EXISTS
FOR ()-[r:APPEAL_FROM]-()
REQUIRE r.edge_id IS UNIQUE;

CREATE CONSTRAINT results_in_edge_id_unique IF NOT EXISTS
FOR ()-[r:RESULTS_IN]-()
REQUIRE r.edge_id IS UNIQUE;

CREATE CONSTRAINT seeks_remedy_edge_id_unique IF NOT EXISTS
FOR ()-[r:SEEKS_REMEDY]-()
REQUIRE r.edge_id IS UNIQUE;

CREATE CONSTRAINT has_opinion_edge_id_unique IF NOT EXISTS
FOR ()-[r:HAS_OPINION]-()
REQUIRE r.edge_id IS UNIQUE;

CREATE CONSTRAINT has_motion_edge_id_unique IF NOT EXISTS
FOR ()-[r:HAS_MOTION]-()
REQUIRE r.edge_id IS UNIQUE;

// ---------------------------------------------------------------------------
// RANGE INDEXES FOR FILTERING
// ---------------------------------------------------------------------------

CREATE RANGE INDEX case_decision_date_idx IF NOT EXISTS
FOR (n:Case) ON (n.decision_date);

CREATE RANGE INDEX case_jurisdiction_date_idx IF NOT EXISTS
FOR (n:Case) ON (n.jurisdiction_id, n.decision_date);

CREATE RANGE INDEX case_court_date_idx IF NOT EXISTS
FOR (n:Case) ON (n.court_id, n.decision_date);

CREATE RANGE INDEX case_precedential_status_idx IF NOT EXISTS
FOR (n:Case) ON (n.precedential_status);

CREATE RANGE INDEX case_publication_status_idx IF NOT EXISTS
FOR (n:Case) ON (n.publication_status);

CREATE RANGE INDEX case_procedural_posture_idx IF NOT EXISTS
FOR (n:Case) ON (n.procedural_posture);

CREATE RANGE INDEX case_standard_of_review_idx IF NOT EXISTS
FOR (n:Case) ON (n.standard_of_review);

CREATE RANGE INDEX case_subject_cluster_idx IF NOT EXISTS
FOR (n:Case) ON (n.subject_similarity_cluster);

CREATE RANGE INDEX case_fact_cluster_idx IF NOT EXISTS
FOR (n:Case) ON (n.fact_cluster);

CREATE RANGE INDEX opinion_case_id_idx IF NOT EXISTS
FOR (n:Opinion) ON (n.case_id);

CREATE RANGE INDEX opinion_type_idx IF NOT EXISTS
FOR (n:Opinion) ON (n.opinion_type);

CREATE RANGE INDEX party_normalized_name_idx IF NOT EXISTS
FOR (n:Party) ON (n.normalized_name);

CREATE RANGE INDEX party_type_idx IF NOT EXISTS
FOR (n:Party) ON (n.party_type);

CREATE RANGE INDEX legal_issue_taxonomy_idx IF NOT EXISTS
FOR (n:LegalIssue) ON (n.taxonomy_key);

CREATE RANGE INDEX holding_issue_id_idx IF NOT EXISTS
FOR (n:Holding) ON (n.issue_id);

CREATE RANGE INDEX holding_precedential_weight_idx IF NOT EXISTS
FOR (n:Holding) ON (n.precedential_weight);

CREATE RANGE INDEX provision_citation_idx IF NOT EXISTS
FOR (n:LegalProvision) ON (n.citation);

CREATE RANGE INDEX provision_type_idx IF NOT EXISTS
FOR (n:LegalProvision) ON (n.provision_type);

CREATE RANGE INDEX doctrine_name_idx IF NOT EXISTS
FOR (n:Doctrine) ON (n.doctrine_name);

CREATE RANGE INDEX topic_label_idx IF NOT EXISTS
FOR (n:Topic) ON (n.topic_label);

CREATE RANGE INDEX outcome_disposition_idx IF NOT EXISTS
FOR (n:Outcome) ON (n.disposition);

CREATE RANGE INDEX outcome_winner_idx IF NOT EXISTS
FOR (n:Outcome) ON (n.winner);

CREATE RANGE INDEX outcome_direction_idx IF NOT EXISTS
FOR (n:Outcome) ON (n.direction);

CREATE RANGE INDEX remedy_type_idx IF NOT EXISTS
FOR (n:Remedy) ON (n.remedy_type);

CREATE RANGE INDEX motion_type_idx IF NOT EXISTS
FOR (n:Motion) ON (n.motion_type);

// Relationship filtering / analytics support
CREATE RANGE INDEX cites_case_treatment_idx IF NOT EXISTS
FOR ()-[r:CITES_CASE]-() ON (r.treatment);

CREATE RANGE INDEX cites_case_context_strength_idx IF NOT EXISTS
FOR ()-[r:CITES_CASE]-() ON (r.context_strength);

CREATE RANGE INDEX cites_case_depth_idx IF NOT EXISTS
FOR ()-[r:CITES_CASE]-() ON (r.depth);

// ---------------------------------------------------------------------------
// TEXT INDEXES FOR EXACT / PREFIX FILTERS
// ---------------------------------------------------------------------------

CREATE TEXT INDEX court_name_text_idx IF NOT EXISTS
FOR (n:Court) ON (n.court_name);

CREATE TEXT INDEX judge_name_text_idx IF NOT EXISTS
FOR (n:Judge) ON (n.name);

CREATE TEXT INDEX case_name_text_idx IF NOT EXISTS
FOR (n:Case) ON (n.case_name);

CREATE TEXT INDEX doctrine_name_text_idx IF NOT EXISTS
FOR (n:Doctrine) ON (n.doctrine_name);

CREATE TEXT INDEX topic_label_text_idx IF NOT EXISTS
FOR (n:Topic) ON (n.topic_label);

CREATE TEXT INDEX provision_citation_text_idx IF NOT EXISTS
FOR (n:LegalProvision) ON (n.citation);

// ---------------------------------------------------------------------------
// FULLTEXT INDEXES FOR SEARCH / RETRIEVAL
// ---------------------------------------------------------------------------

CREATE FULLTEXT INDEX case_fulltext_idx IF NOT EXISTS
FOR (n:Case)
ON EACH [n.case_name, n.caption_full, n.facts_text, n.reasoning_text, n.holding_text, n.full_text];

CREATE FULLTEXT INDEX opinion_fulltext_idx IF NOT EXISTS
FOR (n:Opinion)
ON EACH [n.text];

CREATE FULLTEXT INDEX holding_fulltext_idx IF NOT EXISTS
FOR (n:Holding)
ON EACH [n.holding_text];

CREATE FULLTEXT INDEX rule_statement_fulltext_idx IF NOT EXISTS
FOR (n:RuleStatement)
ON EACH [n.rule_text];

CREATE FULLTEXT INDEX legal_issue_fulltext_idx IF NOT EXISTS
FOR (n:LegalIssue)
ON EACH [n.issue_text];

// ---------------------------------------------------------------------------
// OPTIONAL VECTOR INDEXES
//
// Uncomment these if Acquittify stores actual LIST<FLOAT> embeddings in Neo4j.
// If the application stores only embedding IDs, keep these commented out.
// Neo4j vector indexes are created with CREATE VECTOR INDEX ... OPTIONS { indexConfig: ... }.
// ---------------------------------------------------------------------------

// CREATE VECTOR INDEX case_text_embedding_idx IF NOT EXISTS
// FOR (n:Case)
// ON n.text_embedding
// OPTIONS { indexConfig: {
//   `vector.dimensions`: 1536,
//   `vector.similarity_function`: 'cosine'
// }};

// CREATE VECTOR INDEX case_facts_embedding_idx IF NOT EXISTS
// FOR (n:Case)
// ON n.facts_embedding
// OPTIONS { indexConfig: {
//   `vector.dimensions`: 1536,
//   `vector.similarity_function`: 'cosine'
// }};

// CREATE VECTOR INDEX holding_embedding_idx IF NOT EXISTS
// FOR (n:Holding)
// ON n.embedding
// OPTIONS { indexConfig: {
//   `vector.dimensions`: 1536,
//   `vector.similarity_function`: 'cosine'
// }};

// ---------------------------------------------------------------------------
// OPTIONAL ENTERPRISE-ONLY HARDENING
// These are intentionally commented out so the file runs on Community Edition.
// Neo4j Enterprise supports key, existence, and property-type constraints.
// ---------------------------------------------------------------------------

// CREATE CONSTRAINT case_required_dates IF NOT EXISTS
// FOR (n:Case)
// REQUIRE n.decision_date IS NOT NULL;

// CREATE CONSTRAINT case_required_court IF NOT EXISTS
// FOR (n:Case)
// REQUIRE n.court_id IS NOT NULL;

// CREATE CONSTRAINT opinion_required_text IF NOT EXISTS
// FOR (n:Opinion)
// REQUIRE n.text IS NOT NULL;

// CREATE CONSTRAINT legal_issue_required_taxonomy IF NOT EXISTS
// FOR (n:LegalIssue)
// REQUIRE n.taxonomy_key IS NOT NULL;