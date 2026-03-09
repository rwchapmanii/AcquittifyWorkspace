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

check_file "$root_dir/frontend/src/pages/matters/[id].tsx"
check_file "$root_dir/frontend/src/pages/matters/[id]/hotdocs.tsx"
check_file "$root_dir/frontend/src/pages/matters/[id]/exhibits.tsx"
check_file "$root_dir/frontend/src/pages/matters/[id]/witnesses.tsx"
check_file "$root_dir/frontend/src/pages/docs/[docId].tsx"
check_file "$root_dir/frontend/src/components/PriorityBadge.tsx"
check_file "$root_dir/frontend/src/components/DocViewer.tsx"

$PYTHON_BIN - <<'PY'
from pathlib import Path
import os

root = Path(os.environ["ROOT_DIR"])
components = root / "frontend" / "src" / "components"
assert components.exists()
print("Components OK:", [p.name for p in components.iterdir() if p.suffix == ".tsx"])
PY

echo "Step 9 sanity check passed."
