# CourtListener Ingestion Status

- Time: 2026-02-02 20:05:11 UTC
- Process: running

```text
35054 /Library/Frameworks/Python.framework/Versions/3.13/Resources/Python.app/Contents/MacOS/Python -m ingestion_infra.runners.main bulk_ingest --only opinion-clusters --only opinions
```
- State: `ingestion_state.json`

## Bulk Checkpoints
- courts: 35 snapshot(s), latest bulk-data/courts-2025-12-31.csv.bz2 @ row 3355
- dockets: 1 snapshot(s), latest bulk-data/dockets-2022-08-02.csv.bz2 @ row 40061166
- opinion-clusters: 5 snapshot(s), latest bulk-data/opinion-clusters-2022-11-30.csv.bz2 @ row 6307284
- opinions: 1 snapshot(s), latest bulk-data/opinions-2022-08-02.csv.bz2 @ row 6232875

## Log Tail
_Source_: `courtlistener_bulk_ingest.log`

```text
2026-02-02 14:57:05,221 INFO __main__ - Resuming opinions bulk-data/opinions-2022-08-02.csv.bz2 from row 6232876
```
