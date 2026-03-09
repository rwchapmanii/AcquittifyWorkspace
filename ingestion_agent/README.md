# Ingestion Agent

Modular ingestion pipeline for CourtListener opinions and RECAP filings.

## Project structure

```
ingestion_agent/
  __init__.py
  config.py
  main.py
  models/
    __init__.py
    chunk.py
    metadata.py
  sources/
    __init__.py
    courtlistener.py
  parsers/
    __init__.py
    cleaner.py
    sections.py
  chunkers/
    __init__.py
    semantic.py
  utils/
    __init__.py
    text.py
  data/
    state.json
  output/
    chunks.jsonl
```

## Usage

```bash
python -m ingestion_agent.main --since 2020-01-01 --max-pages 2
```

Environment variables:
- `COURTLISTENER_API_TOKEN` (optional but recommended for rate limits)

Output:
- `ingestion_agent/output/chunks.jsonl` (one chunk per line)

## Notes

- This pipeline does not generate embeddings. It only prepares chunked text with metadata.
- TODOs mark where vector DB and PACER integration should plug in.
