#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export ROOT_DIR="$root_dir"
if [[ -n "${PYTHON_BIN:-}" ]]; then
  PYTHON_BIN="$PYTHON_BIN"
elif [[ -x "$root_dir/.venv/bin/python" ]]; then
  PYTHON_BIN="$root_dir/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  PYTHON_BIN="$(command -v python)"
fi
export PYTHON_BIN

check_file() {
  if [[ ! -f "$1" ]]; then
    echo "Missing file: $1" >&2
    exit 1
  fi
}

check_file "$root_dir/backend/app/workers/celery_app.py"
check_file "$root_dir/backend/app/workers/tasks.py"
check_file "$root_dir/backend/app/workers/pipelines.py"

$PYTHON_BIN - <<'PY'
from pathlib import Path
import os
import sys

root = Path(os.environ["ROOT_DIR"])
sys.path.append(str(root / "backend"))

from app.workers.tasks import build_document_chain

chain = build_document_chain("doc-id")
print("Celery chain OK:", chain)
PY

echo "Celery sanity check passed."
