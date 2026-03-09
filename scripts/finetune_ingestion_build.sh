#!/usr/bin/env bash
set -euo pipefail

# End-to-end ingestion model build: convert LoRA -> update Modelfile.ingestion -> ollama create
# Usage: scripts/finetune_ingestion_build.sh [adapter_dir] [gguf_out] [model_name]

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

ADAPTER_DIR="${1:-$ROOT_DIR/finetune/out-qwen-acquittify-ingestion14b}"
GGUF_OUT="${2:-$ROOT_DIR/finetune/adapters/qwen-acquittify-ingestion14b-f16.gguf}"
MODEL_NAME="${3:-qwen-acquittify-ingestion14b}"

BASE_MODEL_ID="${BASE_MODEL_ID:-Qwen/Qwen2.5-14B-Instruct}"
MODELFILE="${MODELFILE:-$ROOT_DIR/finetune/Modelfile.ingestion}"

python3 "$ROOT_DIR/scripts/finetune_convert_lora.py" \
  --adapter-dir "$ADAPTER_DIR" \
  --out "$GGUF_OUT" \
  --base-model-id "$BASE_MODEL_ID"

export MODELFILE GGUF_OUT
python3 - <<'PY'
from pathlib import Path
import os

modelfile = Path(os.environ["MODELFILE"]).resolve()
adapter = Path(os.environ["GGUF_OUT"]).resolve()
rel_adapter = os.path.relpath(adapter, modelfile.parent)

lines = modelfile.read_text(encoding="utf-8").splitlines()
new_lines = []
inserted = False
for line in lines:
    if line.strip().startswith("ADAPTER "):
        new_lines.append(f"ADAPTER {rel_adapter}")
        inserted = True
    else:
        new_lines.append(line)

if not inserted:
    out = []
    placed = False
    for line in new_lines:
        out.append(line)
        if (not placed) and line.strip().startswith("FROM "):
            out.append(f"ADAPTER {rel_adapter}")
            placed = True
    new_lines = out

modelfile.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
print(f"Updated {modelfile} with ADAPTER {rel_adapter}")
PY

ollama create "$MODEL_NAME" -f "$MODELFILE"
