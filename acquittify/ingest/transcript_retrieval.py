from __future__ import annotations

import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple

import numpy as np
import chromadb
from sentence_transformers import SentenceTransformer

from .transcript_storage import get_case_folder
from ..config import EMBEDDING_MODEL_ID, CHROMA_METADATA_EMBEDDING_KEY
from ..chroma_utils import upsert_or_add

_EMBED_MODEL = None
COLLECTION_NAME = "acquittify_transcripts"


def _get_embed_model():
    global _EMBED_MODEL
    if _EMBED_MODEL is None:
        _EMBED_MODEL = SentenceTransformer(EMBEDDING_MODEL_ID)
    return _EMBED_MODEL


def _get_client(chroma_dir: Path) -> chromadb.Client:
    chroma_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(chroma_dir))


def upsert_transcript_chunks_to_chroma(base_dir: Path, case_title: str, chunk_payloads: List[Dict]) -> None:
    case_dir = get_case_folder(base_dir, case_title)
    chroma_dir = case_dir / "chroma"
    client = _get_client(chroma_dir)
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine", CHROMA_METADATA_EMBEDDING_KEY: EMBEDDING_MODEL_ID},
    )
    try:
        collection.modify(metadata={"hnsw:space": "cosine", CHROMA_METADATA_EMBEDDING_KEY: EMBEDDING_MODEL_ID})
    except Exception:
        pass

    texts = [payload.get("text", "") for payload in chunk_payloads]
    embeddings = _get_embed_model().encode(texts).tolist()
    ids = [payload.get("chunk_id") for payload in chunk_payloads]
    metadatas = []
    for payload in chunk_payloads:
        raw_meta = {
            "case_title": payload.get("case_title"),
            "docket_number": payload.get("docket_number"),
            "document_type": payload.get("document_type"),
            "source_file": payload.get("source_file"),
            "witness": payload.get("witness"),
            "witness_type": payload.get("witness_type"),
            "exam": payload.get("exam"),
            "questioner": payload.get("questioner"),
            "transcript_page": payload.get("transcript_page"),
            "page_id": payload.get("page_id"),
            "citation": payload.get("citation"),
            "chunk_id": payload.get("chunk_id"),
        }
        clean_meta = {k: v for k, v in raw_meta.items() if v is not None}
        metadatas.append(clean_meta)

    batch_size = 200
    for start in range(0, len(ids), batch_size):
        end = min(start + batch_size, len(ids))
        upsert_or_add(
            collection,
            ids=ids[start:end],
            documents=texts[start:end],
            embeddings=embeddings[start:end],
            metadatas=metadatas[start:end],
        )

    try:
        client.persist()
    except AttributeError:
        pass


def search_transcripts(
    case_title: str,
    query: str,
    k: int = 10,
    filters: Optional[Dict] = None,
    base_dir: Optional[Path] = None,
) -> List[Dict]:
    filters = filters or {}
    base_dir = base_dir or Path("data/transcripts")
    case_dir = get_case_folder(base_dir, case_title)
    chroma_dir = case_dir / "chroma"
    index_path = case_dir / "index.json"
    if not index_path.exists():
        return []

    client = _get_client(chroma_dir)
    collection = client.get_or_create_collection(name=COLLECTION_NAME)

    where: Dict = {"case_title": case_title}
    if filters.get("witness"):
        where["witness"] = filters.get("witness")
    if filters.get("witness_type"):
        where["witness_type"] = filters.get("witness_type")
    if filters.get("exam"):
        where["exam"] = filters.get("exam")

    query_embedding = _get_embed_model().encode([query]).tolist()[0]
    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=max(k * 2, 10),
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    docs = result.get("documents", [[]])[0]
    metas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]

    results: List[Dict] = []
    for idx, text in enumerate(docs):
        meta = metas[idx] if idx < len(metas) else {}
        if filters.get("page_range"):
            start, end = filters["page_range"]
            page = meta.get("transcript_page")
            if page is None or page < start or page > end:
                continue
        score = 1.0 - float(distances[idx]) if idx < len(distances) else 0.0
        results.append({
            "score": score,
            "chunk_id": meta.get("chunk_id"),
            "text": text,
            "citation": meta.get("citation", ""),
            "metadata": meta,
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:k]
