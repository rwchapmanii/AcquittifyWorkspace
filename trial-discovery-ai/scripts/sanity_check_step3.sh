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

check_file "$root_dir/backend/app/services/ingest.py"
check_file "$root_dir/backend/app/storage/dropbox.py"
check_file "$root_dir/backend/app/api/routes/ingest.py"

$PYTHON_BIN - <<'PY'
from pathlib import Path
import os
import sys

root = Path(os.environ["ROOT_DIR"])
backend = root / "backend"
sys.path.insert(0, str(backend))
if "" in sys.path:
    sys.path.remove("")

from app.services.ingest import ingest_dropbox_folder  # noqa: F401
from app.storage.dropbox import DropboxClient  # noqa: F401

print("Imports OK for Step 3 ingest components.")
PY

echo "Step 3 sanity check passed."
