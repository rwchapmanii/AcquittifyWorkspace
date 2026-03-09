#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="${1:-acquittify-data}"
CHROMA_DIR="${2:-Corpus/Chroma}"
LOG_PATH="${3:-reports/ingest_CAP_progress.jsonl}"

env OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  PYTHONPATH=. \
  .venv/bin/python scripts/ingest_cap_jsonl.py \
  --base-dir "$BASE_DIR" \
  --chroma-dir "$CHROMA_DIR" \
  --limit 1 \
  --slugs us \
  --min-year 1975 \
  --sort-desc \
  --progress-log "$LOG_PATH" \
  --progress-interval 1

if [[ ! -s "$LOG_PATH" ]]; then
  echo "Progress log not written: $LOG_PATH"
  exit 1
fi

tail -n 1 "$LOG_PATH"
