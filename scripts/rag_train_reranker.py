#!/usr/bin/env python3
"""Train a cross-encoder reranker using sentence-transformers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

from sentence_transformers import CrossEncoder, InputExample
from sentence_transformers.cross_encoder.evaluation import CECorrelationEvaluator
from torch.utils.data import DataLoader


def _load_examples(path: Path) -> List[InputExample]:
    examples: List[InputExample] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            query = (row.get("query") or "").strip()
            doc = (row.get("doc") or "").strip()
            if not query or not doc:
                continue
            label = float(row.get("label", 0))
            examples.append(InputExample(texts=[query, doc], label=label))
    return examples


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a reranker cross-encoder.")
    parser.add_argument("--train", required=True, type=Path, help="Train JSONL")
    parser.add_argument("--val", type=Path, default=None, help="Validation JSONL")
    parser.add_argument(
        "--base-model",
        default="cross-encoder/ms-marco-MiniLM-L-6-v2",
        help="Base cross-encoder model",
    )
    parser.add_argument("--output-dir", required=True, type=Path, help="Output directory")
    parser.add_argument("--epochs", type=int, default=1, help="Training epochs")
    parser.add_argument("--batch-size", type=int, default=8, help="Batch size")
    parser.add_argument("--warmup-ratio", type=float, default=0.1, help="Warmup ratio")
    args = parser.parse_args()

    train_examples = _load_examples(args.train)
    if not train_examples:
        raise SystemExit("No training examples found.")

    val_examples = _load_examples(args.val) if args.val and args.val.exists() else []

    model = CrossEncoder(args.base_model, num_labels=1)

    train_loader = DataLoader(train_examples, shuffle=True, batch_size=args.batch_size)
    warmup_steps = int(len(train_loader) * args.epochs * args.warmup_ratio)

    evaluator = None
    if val_examples:
        evaluator = CECorrelationEvaluator.from_input_examples(val_examples, name="val")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    model.fit(
        train_dataloader=train_loader,
        evaluator=evaluator,
        epochs=args.epochs,
        warmup_steps=warmup_steps,
        output_path=str(args.output_dir),
        show_progress_bar=True,
    )


if __name__ == "__main__":
    main()
