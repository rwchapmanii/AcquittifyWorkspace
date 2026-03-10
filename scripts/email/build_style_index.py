#!/usr/bin/env python3
"""Create an embedding index of exemplar sent emails for retrieval."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

CORPUS = Path("~/.openclaw/email_style/sent.jsonl").expanduser()
INDEX_DIR = Path("~/.openclaw/email_style").expanduser()
EMBED_FILE = INDEX_DIR / "exemplars_embeddings.npz"
META_FILE = INDEX_DIR / "exemplars_meta.jsonl"


def load_corpus(path: Path, limit: int | None) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            rows.append(json.loads(line))
            if limit and len(rows) >= limit:
                break
    return rows


def build_index(limit: int | None) -> None:
    rows = load_corpus(CORPUS, limit)
    model = SentenceTransformer("all-MiniLM-L6-v2")
    texts = [f"Subject: {row.get('subject','') }\n\n{row['body']}" for row in rows]
    embeddings = model.encode(texts, batch_size=32, show_progress_bar=True)
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(EMBED_FILE, embeddings=embeddings)
    with META_FILE.open("w", encoding="utf-8") as fh:
        for row, text in zip(rows, texts):
            meta = {
                "id": row["id"],
                "subject": row.get("subject"),
                "preview": text[:500],
            }
            fh.write(json.dumps(meta, ensure_ascii=False) + "\n")
    print(f"Wrote {EMBED_FILE} and {META_FILE}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build style exemplar embeddings")
    parser.add_argument("--limit", type=int, default=300)
    args = parser.parse_args()
    limit = args.limit if args.limit > 0 else None
    build_index(limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
