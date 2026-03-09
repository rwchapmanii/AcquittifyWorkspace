from __future__ import annotations

from typing import Optional

from .config import (
    CHROMA_COLLECTION,
    CHROMA_DISTANCE,
    CHROMA_METADATA_EMBEDDING_KEY,
    EMBEDDING_MODEL_ID,
)


def get_or_create_collection(client, name: Optional[str] = None):
    collection_name = name or CHROMA_COLLECTION
    metadata = {
        "hnsw:space": CHROMA_DISTANCE,
        CHROMA_METADATA_EMBEDDING_KEY: EMBEDDING_MODEL_ID,
    }
    collection = client.get_or_create_collection(name=collection_name, metadata=metadata)
    try:
        collection.modify(metadata=metadata)
    except Exception:
        pass
    return collection


def upsert_or_add(collection, **kwargs):
    if hasattr(collection, "upsert"):
        try:
            return collection.upsert(**kwargs)
        except Exception:
            pass
    return collection.add(**kwargs)
