# CourtListener Ingestion Status

- Time: 2026-02-06 17:43:27 UTC
- Process: not detected
- State: `ingestion_state.json`

## Bulk Checkpoints
- courts: 35 snapshot(s), latest bulk-data/courts-2025-12-31.csv.bz2 @ row 3355
- dockets: 1 snapshot(s), latest bulk-data/dockets-2022-08-02.csv.bz2 @ row 40061166
- opinion-clusters: 5 snapshot(s), latest bulk-data/opinion-clusters-2022-11-30.csv.bz2 @ row 6307284
- opinions: 1 snapshot(s), latest bulk-data/opinions-2022-08-02.csv.bz2 @ row 6232875

## Database Checkpoints
- DB: latest checkpoints:
  bulk_csv opinions bulk-data/opinions-2022-08-02.csv.bz2 @ 6232875 (2026-02-02 22:18:38 UTC)
  bulk_csv dockets bulk-data/dockets-2022-08-02.csv.bz2 @ 40061166 (2026-02-02 01:40:31 UTC)
  bulk_csv courts bulk-data/courts-2025-12-31.csv.bz2 @ 3355 (2026-02-02 00:23:53 UTC)
  bulk_csv courts bulk-data/courts-2025-12-02.csv.bz2 @ 3355 (2026-02-02 00:23:53 UTC)
  bulk_csv courts bulk-data/courts-2025-10-31.csv.bz2 @ 3355 (2026-02-02 00:23:52 UTC)
  bulk_csv courts bulk-data/courts-2025-10-09.csv.bz2 @ 3355 (2026-02-02 00:23:52 UTC)
  bulk_csv courts bulk-data/courts-2025-09-04.csv.bz2 @ 3355 (2026-02-02 00:23:52 UTC)
  bulk_csv courts bulk-data/courts-2025-07-02.csv.bz2 @ 3354 (2026-02-02 00:23:51 UTC)

## Log Tail
_Source_: `courtlistener_bulk_ingest.log`

```text
2026-02-02 11:47:29,804 INFO __main__ - Checkpointed opinions bulk-data/opinions-2022-08-02.csv.bz2 at row 6225245
2026-02-02 11:47:39,519 INFO __main__ - Checkpointed opinions bulk-data/opinions-2022-08-02.csv.bz2 at row 6226245
2026-02-02 11:47:55,908 INFO __main__ - Checkpointed opinions bulk-data/opinions-2022-08-02.csv.bz2 at row 6227245
2026-02-02 11:48:13,103 INFO __main__ - Checkpointed opinions bulk-data/opinions-2022-08-02.csv.bz2 at row 6228245
2026-02-02 11:48:28,238 INFO __main__ - Checkpointed opinions bulk-data/opinions-2022-08-02.csv.bz2 at row 6229245
2026-02-02 11:48:43,207 INFO __main__ - Checkpointed opinions bulk-data/opinions-2022-08-02.csv.bz2 at row 6230245
2026-02-02 11:49:00,912 INFO __main__ - Checkpointed opinions bulk-data/opinions-2022-08-02.csv.bz2 at row 6231245
2026-02-02 11:49:19,414 INFO __main__ - Checkpointed opinions bulk-data/opinions-2022-08-02.csv.bz2 at row 6232245
2026-02-02 12:04:29,561 WARNING __main__ - Timeout streaming opinions bulk-data/opinions-2022-08-02.csv.bz2 at row 6232875 (1/15): Read timeout on endpoint URL: "None"
2026-02-02 12:04:34,580 INFO __main__ - Resuming opinions bulk-data/opinions-2022-08-02.csv.bz2 from row 6232876
2026-02-02 13:24:42,801 WARNING __main__ - Timeout streaming opinions bulk-data/opinions-2022-08-02.csv.bz2 at row 6232875 (2/15): Read timeout on endpoint URL: "None"
2026-02-02 13:24:52,832 INFO __main__ - Resuming opinions bulk-data/opinions-2022-08-02.csv.bz2 from row 6232876
2026-02-02 14:44:16,113 WARNING __main__ - Timeout streaming opinions bulk-data/opinions-2022-08-02.csv.bz2 at row 6232875 (3/15): Read timeout on endpoint URL: "None"
2026-02-02 14:44:31,460 INFO __main__ - Resuming opinions bulk-data/opinions-2022-08-02.csv.bz2 from row 6232876
2026-02-02 14:57:05,219 INFO __main__ - Starting bulk snapshot bulk-data/opinions-2022-08-02.csv.bz2 for opinions
2026-02-02 14:57:05,221 INFO __main__ - Resuming opinions bulk-data/opinions-2022-08-02.csv.bz2 from row 6232876
2026-02-02 15:41:42,214 WARNING __main__ - Timeout streaming opinions bulk-data/opinions-2022-08-02.csv.bz2 at row 6232875 (1/15): Read timeout on endpoint URL: "None"
2026-02-02 15:41:47,243 INFO __main__ - Resuming opinions bulk-data/opinions-2022-08-02.csv.bz2 from row 6232876
2026-02-02 17:18:38,681 WARNING __main__ - Timeout streaming opinions bulk-data/opinions-2022-08-02.csv.bz2 at row 6232875 (2/15): Read timeout on endpoint URL: "None"
2026-02-02 17:18:48,713 INFO __main__ - Resuming opinions bulk-data/opinions-2022-08-02.csv.bz2 from row 6232876
```
