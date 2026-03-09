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

check_file "$root_dir/README.md"
check_file "$root_dir/docker-compose.yml"
check_file "$root_dir/.env.example"
check_file "$root_dir/backend/app/main.py"
check_file "$root_dir/frontend/package.json"
check_file "$root_dir/docs/MVP_SPEC.md"

$PYTHON_BIN - <<'PY'
from pathlib import Path
import os

root = Path(os.environ["ROOT_DIR"])
main_py = root / "backend" / "app" / "main.py"
print(f"Found backend entrypoint: {main_py}")
PY

echo "Sanity check passed."
