#!/usr/bin/env bash
set -euo pipefail

OUT_PATH="${1:-reports/courtlistener_ingest_status.md}"
INTERVAL="${2:-5}"

PYTHON=".venv/bin/python"
if [[ ! -x "${PYTHON}" ]]; then
  PYTHON="python3"
fi

exec "${PYTHON}" scripts/courtlistener_ingest_status.py \
  --format md \
  --output "${OUT_PATH}" \
  --watch "${INTERVAL}"
