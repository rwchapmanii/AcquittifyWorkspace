#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DEFAULT_DSN="postgresql://acquittify:acquittify@localhost:5432/courtlistener"
export COURTLISTENER_DB_DSN="${COURTLISTENER_DB_DSN:-$DEFAULT_DSN}"

if [[ ! -x ".venv/bin/python" ]]; then
  echo "Missing .venv python at .venv/bin/python"
  exit 1
fi

.venv/bin/python -m pytest -q
