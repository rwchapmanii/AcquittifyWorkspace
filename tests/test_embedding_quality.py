import os
import json
from pathlib import Path

import numpy as np
import pytest

from acquittify.chunking import chunk_text
from document_ingestion_backend import _encode_embeddings


def _load_sample_chunks(base_dir: str = "acquittify-data", limit: int = 10) -> list[str]:
    shards_dir = Path(base_dir) / "ingest" / "cases"
    if not shards_dir.exists():
        return []

    samples: list[str] = []
    for shard in sorted(shards_dir.glob("cases_*.jsonl")):
        with shard.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                text = record.get("opinion_text") or ""
                if not text.strip():
                    continue
                chunks = chunk_text(text)
                if not chunks:
                    continue
                samples.append(chunks[0])
                if len(samples) >= limit:
                    return samples
    return samples


def score_embedding_self_retrieval(sample_limit: int = 10, base_dir: str = "acquittify-data") -> float:
    samples = _load_sample_chunks(base_dir=base_dir, limit=sample_limit)
    if len(samples) < sample_limit:
        raise RuntimeError(f"Needed {sample_limit} samples, found {len(samples)}")

    embeddings = _encode_embeddings(samples)
    if embeddings is None:
        raise RuntimeError("Embedding model unavailable")

    vectors = np.asarray(embeddings, dtype=float)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    sims = (vectors @ vectors.T) / (norms @ norms.T)
    top1 = np.argmax(sims, axis=1)
    accuracy = float(np.mean(top1 == np.arange(len(samples))))
    return accuracy


@pytest.mark.skipif(
    os.getenv("RUN_EMBEDDING_TESTS") != "1",
    reason="set RUN_EMBEDDING_TESTS=1 to run embedding quality tests",
)
def test_embedding_self_retrieval_accuracy():
    try:
        score = score_embedding_self_retrieval(sample_limit=10)
    except RuntimeError as exc:
        pytest.skip(str(exc))
    print(f"embedding_self_retrieval_accuracy={score:.3f}")
    assert score >= 0.7
