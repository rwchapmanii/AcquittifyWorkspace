---
name: Review (Acquittify)
description: Review diffs for correctness, retrieval safety, and QA integrity.
---

Review checklist:
- Does ingestion use the same embedding model as retrieval?
- Are chunk sizes/overlap as configured?
- Are Chroma collections non-empty and metadata-filtered?
- Do QA eval items have gold source ids and answer targets?
- Any changes that risk "silent failure" (empty collection, mismatched dims, etc.)?
