from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Embeddings / Chroma
EMBEDDING_MODEL_ID = "all-MiniLM-L6-v2"
CHROMA_COLLECTION = "acquittify_corpus"
CHROMA_DISTANCE = "cosine"
CHROMA_METADATA_EMBEDDING_KEY = "embedding_model"

# Chunking
CHUNK_SIZE_CHARS = 1100
CHUNK_OVERLAP_RATIO = 0.18
CHUNK_MIN_CHARS = 350
