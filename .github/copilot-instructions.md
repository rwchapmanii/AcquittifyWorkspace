# Acquittify AI agent instructions

Follow root COPILOT_INSTRUCTIONS.md in addition to this file.

## Non-negotiables (project rules)
- No “big bang” refactors; keep changes small and reviewable.
- Do NOT modify raw CourtListener ingest tables (schema `raw` is immutable). All DB changes via migrations; new derived tables go in schema `derived`.
- Never change retrieval or embedding code without adding/adjusting a sanity-check test or script.
- Use shared config values in [acquittify/config.py](acquittify/config.py) for embedding model, chunking, and collection names.
- Never embed full opinions; only embed derived chunks.
- Always store/pass metadata: source ids, court/circuit, year, posture, citations, SoR, burden, is_holding/is_dicta, favorability, taxonomy codes.

## Architecture & data flow (big picture)
- Streamlit UI lives in [app.py](app.py); it calls `classify_intent()` and then query expansion in [acquittify_query.py](acquittify_query.py).
- Taxonomy routing happens before retrieval via `classify_question()` in [acquittify_router.py](acquittify_router.py) to produce a controlled `primary_area`.
- Retrieval in [acquittify_retriever.py](acquittify_retriever.py) applies metadata filters by legal area **before** vector search; Chroma fallback reads from `Corpus/Chroma/documents`.
- Transcript retrieval is separate: transcript chunks live under `data/transcripts/<CASE>_Transcripts/` and are searched by [acquittify/ingest/transcript_retrieval.py](acquittify/ingest/transcript_retrieval.py). When citing transcript excerpts, include the `citation` field verbatim.

## Ingestion pipelines (intentionally separate)
- [ingestion_agent/](ingestion_agent/) prepares chunked text + metadata only (no embeddings). Example: `python -m ingestion_agent.main --since 2020-01-01 --max-pages 2`.
- [ingestion_infra/](ingestion_infra/) handles CourtListener bulk/API ingestion into staging (no parsing/chunking/embedding). Example: `python -m ingestion_infra.runners.main bulk_ingest`.

## Local run & services
- Streamlit app is launched by [launch_acquittify.sh](launch_acquittify.sh) (fixed port 8501). Use it as the canonical local run path.
- Local services are managed via docker compose; keep commands explicit when instructing migrations/tests.

## Agent tooling conventions
- Ponner-Investigator uses a local Ollama model (`deepseek-r1:8b`) via [agent-cornelius/ollama_client.py](agent-cornelius/ollama_client.py) with env in [agent-cornelius/.env](agent-cornelius/.env) (see [README.md](README.md)).
- If a user asks to search or document in Obsidian, explicitly list the Obsidian tools from [AGENTS.md](AGENTS.md) and ask which one they want. Use `obsidian_search_replace` for global edits (default `dry_run=true`).

## Change safety & delivery
- Prefer adding new modules over rewriting existing ones unless asked.
- If unsure about an existing function signature or data structure, stop and ask for confirmation using actual code references.
- Include a short “what changed” note in the PR/commit message and provide a test or simple sanity-check script that proves the change works.
