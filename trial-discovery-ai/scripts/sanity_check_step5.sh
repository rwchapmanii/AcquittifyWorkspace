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

check_file "$root_dir/backend/app/services/chunk_and_embed.py"
check_file "$root_dir/backend/app/services/chunking.py"
check_file "$root_dir/backend/app/services/embedding.py"

$PYTHON_BIN - <<'PY'
from pathlib import Path
import os
import sys

root = Path(os.environ["ROOT_DIR"])
sys.path.append(str(root / "backend"))

from app.services.chunking import chunk_text

chunks = chunk_text("hello world" * 50, chunk_size=50, overlap=10)
assert chunks
print(f"Chunks created: {len(chunks)}")
PY

echo "Step 5 sanity check passed."
