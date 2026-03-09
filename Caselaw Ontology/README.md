# Caselaw Ontology (Private Reference)

This directory is intentionally a placeholder. The actual Caselaw Ontology assets live in a private vault (autonomy policies, Neo4j schema files, ingestion scripts, and model prompts) and **must not be committed to Git**.

What lives offline:

1. **Autonomy policy + extensions** – YAML/Cypher policies that govern how holdings are promoted into the ontology, including the `acquittify_autonomy_policy_v1_2026-03-08.yaml` lineage and experimental extensions.
2. **Graph contracts & schema** – Mermaid/Markdown docs (`acquittify_graph_contract.md`, `acquittify_neo4j_schema.cypher`) that describe the node/edge taxonomy and Neo4j migration routines.
3. **Extraction + ingest helpers** – Python workers such as `acquittify_ingest.py` and `acquittify_case_extraction_models.py` that orchestrate ontology drafting before data hits Postgres/Neo4j.
4. **Autonomous improvement notes** – Research logs ("Autonomous improvement method", "autonomy_extensions") that document how the ontology self-audits and when humans are required to sign off.

If you need access to the real files, sync from the secure storage bucket (`s3://acq-proprietary-ontology/<date>/`) or ask Ron for the latest bundle. Never check the raw assets into this repo—only update this README if the theory or file list changes.
