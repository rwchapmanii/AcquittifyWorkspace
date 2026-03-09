# Peregrine Bootstrap Refresh Prompt
<!-- ACQUITTIFY_BOOTSTRAP_REFRESH_PROMPT_VERSION:2.4 -->

## Refresh Commands
- `/bootstrap refresh`
- `/bootstrap refresh --case "."`

## Additions-Only Delta Analysis Prompt (Paste Into OpenClaw/Peregrine)
```text
You are Peregrine inside Acquittify. Execute a BOOTSTRAP REFRESH for the active case root.

Critical routing:
- This request is NOT OpenClaw workspace initialization.
- Do NOT respond with AGENTS.md / BOOTSTRAP.md / SOUL.md startup ritual summaries.
- Treat `/bootstrap refresh` as Acquittify deep bootstrap refresh.

Execution target:
- Mode: deep
- Operation: refresh
- Case root: active vault root (`.` unless user supplied --case path).
- Schema contract: Acquittify Ontology Schema v1.2.

Refresh requirements:
1) Load prior source index from /Casefile/00_Metadata/bootstrap_source_index.json.
2) Scan the current source casefile and build a new source index snapshot.
3) Compute deltas: new documents, updated documents, removed documents.
4) Analyze each new/updated document for ontology impact:
   - likely document type
   - count references
   - explicit transcript witness-identification hits
   - witness-list/interviewee signals
   - attorney/counsel signals
5) Re-run deep ontology synthesis so all impacted witness/count/exhibit/relationship nodes are current.
6) Write refresh delta report to /Casefile/00_Metadata/bootstrap_refresh_report.json.

Completion response format:
- Bootstrap refresh completed.
- Case root:
- Mode: deep
- New documents:
- Updated documents:
- Removed documents:
- Delta report:
- Source index:
- Workspace note:
- Warnings: <if any>

If OpenClaw drifts to startup-routine output, immediately comply by running:
/bootstrap refresh --case "."
```
