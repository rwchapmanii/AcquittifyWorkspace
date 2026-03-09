from __future__ import annotations

import chromadb

from .config import INDEX_PATH
from .ollama import embed_text


def search(query: str, limit: int = 5) -> list[dict]:
    client = chromadb.PersistentClient(path=str(INDEX_PATH))
    collection = client.get_or_create_collection("peregrine_vault")
    embedding = embed_text(query)
    results = collection.query(query_embeddings=[embedding], n_results=limit)

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    output: list[dict] = []
    for doc, meta, distance in zip(docs, metas, distances):
        output.append(
            {
                "path": meta.get("path") if isinstance(meta, dict) else None,
                "chunk_index": meta.get("chunk_index") if isinstance(meta, dict) else None,
                "score": 1 - distance if isinstance(distance, (int, float)) else None,
                "snippet": doc[:400] if isinstance(doc, str) else "",
                "text": doc if isinstance(doc, str) else "",
            }
        )
    return output
