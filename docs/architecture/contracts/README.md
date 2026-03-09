# Graph Contract Assets

This directory stores the source contract artifacts for Neo4j migration.

Files:
- `acquittify_graph_contract.md`: high-level graph contract assumptions and loader sequence.
- `acquittify_autonomous_improvement_method.md`: autonomous testing and ontology improvement method.

Related implementation files:
- `acquittify/ontology/neo4j/case_extraction_models.py`: Pydantic extraction + graph projection models.
- `acquittify/ontology/neo4j/schema/acquittify_neo4j_schema.cypher`: Neo4j 5.x schema constraints and indexes.
- `acquittify/ontology/neo4j/schema/acquittify_autonomy_extensions.cypher`: governance/evaluation graph extensions.
- `acquittify/ontology/neo4j/policies/acquittify_autonomy_policy_v1_2026-03-08.yaml`: strict policy thresholds and veto rules.

Validation helper:
- `scripts/validate_case_extraction_envelope.py`
- `scripts/nightly_neo4j_extraction_validate.py`
- `scripts/evaluate_ontology_autonomy_policy.py`
