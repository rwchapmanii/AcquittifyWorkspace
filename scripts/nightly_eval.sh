#!/usr/bin/env bash
set -euo pipefail

PY="./.venv/bin/python"
LOG="eval/nightly.log"

mkdir -p eval
{
  echo "==== Nightly eval start: $(date) ===="

  # 1) sanity check chroma
  $PY scripts/chroma_sanity_check.py

  # 2) generate QA eval with deterministic seed + fixed count
  $PY scripts/qa_eval_generate.py \
    --output eval/qa_eval.jsonl \
    --count 200 \
    --seed 42

  # 3) run eval report
  $PY scripts/qa_eval_run.py \
    --eval eval/qa_eval.jsonl \
    --report eval/qa_eval_report_new.json

  echo "==== Nightly eval end: $(date) ===="
} | tee -a "$LOG"
