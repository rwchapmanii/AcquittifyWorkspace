# Acquittify CAP Ingestion (static.case.law)

This guide downloads **only** the federal reporters from https://static.case.law, normalizes them into Acquittify JSONL shards, and produces a verifiable manifest with checksums.

## Reporters included (federal only)
- alaska-fed
- ccpa
- cma
- ct-cust
- ct-intl-trade
- cust-ct
- d-haw
- ed-pa
- f
- f-appx
- f-cas
- f-supp
- f-supp-2d
- f-supp-3d
- f2d
- f3d
- fed-cl
- frd
- n-mar-i-commw
- pr-fed
- us
- us-app-dc
- us-ct-cl
- vet-app

## Output layout
```
./acquittify-data/
  raw/
    static.case.law/
  staging/
    extracted/
  ingest/
    cases/
    manifest/
  logs/
```

## Step A — Download raw
### Preferred: Python downloader (resumable + verified)
The downloader is polite (1 request/sec average), retries with exponential backoff, and can be re-run safely.

- Script: scripts/download_federal.py
- Manifest: acquittify-data/logs/download_manifest.jsonl
- Missing URL reports: acquittify-data/logs/missing_<slug>.txt

Run:
```
.venv/bin/python scripts/download_federal.py --base-dir acquittify-data
```

Optional: override rate or limit slugs
```
.venv/bin/python scripts/download_federal.py --base-dir acquittify-data --rate 1.0 --slugs f f2d f3d
```

### Optional: wget (if installed)
Target each slug individually; do NOT mirror the entire site.
```
mkdir -p acquittify-data/raw/static.case.law acquittify-data/logs
wget -nv -P acquittify-data/raw/static.case.law \
  https://static.case.law/ReportersMetadata.json \
  https://static.case.law/VolumesMetadata.json \
  https://static.case.law/JurisdictionsMetadata.json

wget -m -np -nH --cut-dirs=0 -P acquittify-data/raw \
  --wait=1 --random-wait --tries=5 --timeout=30 \
  --no-verbose -o acquittify-data/logs/wget_f3d.log \
  https://static.case.law/f3d/
```

## Step B — Normalize to Acquittify JSONL
Produces JSONL shards in acquittify-data/ingest/cases with a ~250MB size target (or 200k records).

Run:
```
.venv/bin/python scripts/normalize_cap.py --base-dir acquittify-data
```

## Step B2 — Ingest JSONL into Chroma
This step wires the normalized JSONL into the existing Acquittify ingestion pipeline
with consistent chunking, taxonomy analysis, and metadata enrichment.

Run:
```
.venv/bin/python scripts/ingest_cap_jsonl.py --base-dir acquittify-data --chroma-dir Corpus/Chroma
```

Schema emitted:
```
{
  "source": "cap-static-case-law",
  "reporter_slug": "<slug>",
  "jurisdiction": "...",
  "court": "...",
  "decision_date": "...",
  "docket_number": "...",
  "case_name": "...",
  "citations": [...],
  "volume": "...",
  "page": "...",
  "opinion_text": "...",
  "opinion_text_type": "plain|html|xml|unknown",
  "cap_id": "...",
  "download_url": "<original URL>",
  "sha256_raw_file": "<sha256 of raw file>",
  "error": "missing_opinion_text" (only when needed)
}
```

## Step C — Manifest + verification
After normalization, the script writes:
- acquittify-data/ingest/manifest/manifest.json
- acquittify-data/ingest/manifest/checksums.txt

Run sanity check:
```
.venv/bin/python scripts/cap_ingest_sanity.py
```

Optional loader sanity check (after normalization):
```
.venv/bin/python scripts/cap_ingest_loader_sanity.py
```

If missing URLs are detected during download, the script writes
acquittify-data/logs/missing_<slug>.txt and exits non-zero, while preserving logs.

## Notes
- Resumable: downloads skip existing files and reuse the manifest log.
- Deterministic: files are crawled and processed in sorted order.
- Polite: 1 request/sec average with backoff on errors.
