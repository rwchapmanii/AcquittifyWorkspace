#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -n "${PYTHON_BIN:-}" ]]; then
  PYTHON_BIN="$PYTHON_BIN"
elif [[ -x "$root_dir/.venv/bin/python" ]]; then
  PYTHON_BIN="$root_dir/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  PYTHON_BIN="$(command -v python)"
fi

while pgrep -f "qa_eval_generate.py" >/dev/null; do
  sleep 30
done

PYTHONPATH="$root_dir" "$PYTHON_BIN" "$root_dir/scripts/qa_eval_run.py" \
  --eval "$root_dir/eval/qa_eval.jsonl" \
  --report "$root_dir/eval/qa_eval_report.json"
