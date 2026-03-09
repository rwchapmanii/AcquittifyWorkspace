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

$PYTHON_BIN - <<'PY'
from pathlib import Path
import os
import sys

root = Path(os.environ["ROOT_DIR"])
sys.path.append(str(root / "backend"))

from app.db.base import Base
from app.db import models  # noqa: F401

expected = {
    "matters",
    "documents",
    "artifacts",
    "chunks",
    "pass_runs",
    "entities",
    "document_entities",
    "exhibits",
    "user_actions",
}

actual = set(Base.metadata.tables.keys())
missing = expected - actual
extra = actual - expected

if missing:
    raise SystemExit(f"Missing tables: {sorted(missing)}")

print("Tables OK:", sorted(actual))
if extra:
    print("Extra tables:", sorted(extra))
PY

echo "Step 2 sanity check passed."
