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

check_file "$root_dir/backend/app/services/pass2.py"
check_file "$root_dir/backend/app/core/llm/schemas.py"
check_file "$root_dir/backend/app/core/llm/prompts.py"

$PYTHON_BIN - <<'PY'
from pathlib import Path
import os
import sys

root = Path(os.environ["ROOT_DIR"])
sys.path.append(str(root / "backend"))

from app.core.llm.schemas import Pass2Schema

schema = Pass2Schema.model_json_schema()
assert "properties" in schema
print("Pass2 schema OK.")
PY

echo "Step 7 sanity check passed."
