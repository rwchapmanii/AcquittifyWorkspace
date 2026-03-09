#!/usr/bin/env bash
set -euo pipefail

export COURTLISTENER_S3_BUCKET="${COURTLISTENER_S3_BUCKET:-com-courtlistener-storage}"
export COURTLISTENER_S3_PREFIX="${COURTLISTENER_S3_PREFIX:-bulk-data}"
export COURTLISTENER_S3_REGION="${COURTLISTENER_S3_REGION:-us-west-2}"
export COURTLISTENER_S3_UNSIGNED="${COURTLISTENER_S3_UNSIGNED:-true}"
export COURTLISTENER_S3_ADDRESSING_STYLE="${COURTLISTENER_S3_ADDRESSING_STYLE:-auto}"
export COURTLISTENER_S3_HTTP_FALLBACK_URL="${COURTLISTENER_S3_HTTP_FALLBACK_URL:-https://storage.courtlistener.com}"
export COURTLISTENER_BULK_DATA_URL="${COURTLISTENER_BULK_DATA_URL:-https://com-courtlistener-storage.s3-us-west-2.amazonaws.com/?delimiter=/&prefix=bulk-data/}"
export COURTLISTENER_DB_DSN="${COURTLISTENER_DB_DSN:-postgresql://acquittify:acquittify@localhost:5432/courtlistener}"

LOG_PATH="${1:-courtlistener_bulk_ingest.log}"
PYTHON=".venv/bin/python"
if [[ ! -x "${PYTHON}" ]]; then
  PYTHON="python3"
fi

STATUS_ENABLED="${COURTLISTENER_STATUS_WATCH_ENABLED:-true}"
STATUS_SECONDS="${COURTLISTENER_STATUS_WATCH_SECONDS:-30}"
STATUS_PATH="${COURTLISTENER_STATUS_LOG_PATH:-reports/courtlistener_ingest_status.md}"
STATUS_LOG="${COURTLISTENER_STATUS_WATCH_LOG:-courtlistener_status_watch.log}"

ONLY_ARGS=(--only opinion-clusters --only opinions)
if [[ "${COURTLISTENER_INCLUDE_OPINION_TEXTS:-false}" == "true" ]]; then
  ONLY_ARGS+=(--only opinion-texts)
fi

nohup "${PYTHON}" -m ingestion_infra.runners.main bulk_ingest \
  "${ONLY_ARGS[@]}" \
  >> "${LOG_PATH}" 2>&1 &
echo $!

if [[ "${STATUS_ENABLED}" == "true" ]]; then
  if ! pgrep -f "scripts/courtlistener_ingest_status.py --format md --output ${STATUS_PATH}" >/dev/null; then
    nohup "${PYTHON}" scripts/courtlistener_ingest_status.py \
      --format md \
      --output "${STATUS_PATH}" \
      --watch "${STATUS_SECONDS}" \
      --db \
      --tail 20 \
      >> "${STATUS_LOG}" 2>&1 &
  fi
fi
