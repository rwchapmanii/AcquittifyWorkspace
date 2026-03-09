#!/usr/bin/env python3
"""Convert a PEFT LoRA adapter to GGUF for Ollama using llama.cpp.

This helper clones llama.cpp if needed and runs convert_lora_to_gguf.py.
"""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LLAMA_DIR = Path(os.environ.get("LLAMA_CPP_DIR", "/tmp/llama.cpp"))
LLAMA_REPO = "https://github.com/ggml-org/llama.cpp.git"


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def ensure_llama_cpp(path: Path) -> Path:
    convert_script = path / "convert_lora_to_gguf.py"
    if convert_script.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    run(["git", "clone", "--depth", "1", LLAMA_REPO, str(path)])
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert PEFT LoRA adapter to GGUF for Ollama")
    parser.add_argument("--adapter-dir", required=True, type=Path, help="Path to PEFT adapter dir")
    parser.add_argument("--out", required=True, type=Path, help="Output GGUF path")
    parser.add_argument(
        "--base-model-id",
        default="Qwen/Qwen2.5-14B-Instruct",
        help="HF model ID for base config",
    )
    parser.add_argument(
        "--base-config-dir",
        type=Path,
        default=None,
        help="Optional local base model config directory (config.json, tokenizer.json)",
    )
    parser.add_argument(
        "--outtype",
        default="f16",
        choices=["f32", "f16", "bf16", "q8_0", "auto"],
        help="GGUF output type",
    )
    parser.add_argument(
        "--llama-cpp-dir",
        type=Path,
        default=DEFAULT_LLAMA_DIR,
        help="Path to llama.cpp clone (will be cloned if missing)",
    )
    args = parser.parse_args()

    adapter_dir = args.adapter_dir.resolve()
    if not adapter_dir.exists():
        raise SystemExit(f"Adapter directory not found: {adapter_dir}")

    if not (adapter_dir / "adapter_config.json").exists():
        raise SystemExit("adapter_config.json not found in adapter directory")

    out_path = args.out.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    llama_dir = ensure_llama_cpp(args.llama_cpp_dir.resolve())
    convert_script = llama_dir / "convert_lora_to_gguf.py"

    cmd = [
        "python3",
        str(convert_script),
        str(adapter_dir),
        "--outfile",
        str(out_path),
        "--outtype",
        args.outtype,
    ]

    if args.base_config_dir:
        cmd.extend(["--base", str(args.base_config_dir.resolve())])
    else:
        cmd.extend(["--base-model-id", args.base_model_id])

    run(cmd)
    print(f"Wrote GGUF adapter: {out_path}")


if __name__ == "__main__":
    main()
