# Acquittify graph contract for Codex

This package includes:
- `acquittify_neo4j_schema.cypher`
- `acquittify_case_extraction_models.py`

## Assumptions
- Neo4j 5.x
- Pydantic v2
- Python 3.11+
- Graph loader uses `MERGE` by `(label, id)` for nodes and `(type, edge_id)` for relationships.

## Normalizations added during conversion
The conceptual YAML had three graph gaps that would produce orphan nodes in Neo4j. The concrete graph contract adds:
- `(:Case)-[:HAS_OPINION]->(:Opinion)`
- `(:Case)-[:HAS_TOPIC]->(:Topic)`
- `(:Case)-[:HAS_MOTION]->(:Motion)`

## Stable identity strategy
- Every node must carry a common `id` property.
- Every relationship must carry a common `edge_id` property.
- Domain-specific ids (`case_id`, `opinion_id`, etc.) are still preserved as regular properties.

## Storage strategy
- Neo4j stores flattened graph properties only.
- Full nested YAML should be persisted separately in object storage or a document store.
- The Pydantic model is the source of truth for extraction validation and YAML serialization.
- `CaseExtractionEnvelope` matches the original top-level `case:` YAML shape.

## Batch-derived edges
These should be created after many cases are loaded, not from a single-case extraction:
- `SAME_ISSUE`
- `SAME_PROVISION`
- `SAME_FACT_CLUSTER`

Reason: they require cross-case comparison and are best computed in a nightly graph analytics pass.

## Recommended loader shape
1. Validate raw extraction with `CaseExtraction`.
2. Persist raw YAML.
3. Convert to `GraphDocument` with `to_graph_document()`.
4. Upsert nodes first.
5. Upsert relationships second.
6. Run post-load jobs:
   - centrality refresh
   - similarity-edge generation
   - doctrine-cluster refresh
   - outcome prediction feature materialization

## Relationship semantics
- `CITES_CASE` is always created when a cited case is known.
- Typed treatment edges (`FOLLOWS`, `DISTINGUISHES`, `LIMITS`, `OVERRULES`, `QUESTIONS`) are added in parallel when the treatment is extracted.
- `RELIES_ON` is only emitted when holding-to-holding linkage is available.

## Loader caveat
Neo4j node properties cannot store nested maps. Keep nested structures flattened or JSON-encoded as strings where needed.