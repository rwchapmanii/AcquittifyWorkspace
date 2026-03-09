# CourtListener Ingestion Infrastructure

Production-grade scaffolding for ingesting CourtListener data from the REST API and quarterly S3 bulk CSV snapshots.

## Project structure

```
ingestion_infra/
  __init__.py
  config.py
  logging_config.py
  runners/
    __init__.py
    main.py
  sources/
    __init__.py
    api_client.py
    s3_bulk.py
  storage/
    __init__.py
    staging_db.py
  change_detection/
    __init__.py
    hasher.py
  checkpoints/
    __init__.py
    state_store.py
  utils/
    __init__.py
    csv_stream.py
```

## Setup

Set configuration using environment variables (see `config.py`).

Public bulk snapshots can be accessed without credentials by setting `COURTLISTENER_S3_UNSIGNED=true` (default).

## Run

```bash
python -m ingestion_infra.runners.main bulk_ingest
python -m ingestion_infra.runners.main api_incremental_update --since 2024-01-01
```

## Notes

- Parsing, chunking, and embedding are intentionally omitted.
- Bulk CSV ingestion is treated as a full snapshot.
- Staging DB stores raw rows/JSON for downstream processing.
