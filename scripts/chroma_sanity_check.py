import argparse
import json
import sys
from pathlib import Path

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from acquittify.config import (
    CHROMA_COLLECTION,
    CHROMA_METADATA_EMBEDDING_KEY,
    EMBEDDING_MODEL_ID,
)
from acquittify.chroma_utils import get_or_create_collection

DEFAULT_CHROMA_DIR = PROJECT_ROOT / "Corpus" / "Chroma"


def _create_client(chroma_dir: Path):
    try:
        return chromadb.PersistentClient(path=str(chroma_dir))
    except Exception:
        try:
            settings = Settings(persist_directory=str(chroma_dir), anonymized_telemetry=False)
            return chromadb.Client(settings)
        except Exception:
            return chromadb.Client()


def _print_collections(client) -> None:
    try:
        collections = client.list_collections()
    except Exception:
        collections = []
    names = []
    for col in collections:
        try:
            names.append(col.name)
        except Exception:
            continue
    print("Collections:", names)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sanity check Chroma collection presence and queryability.")
    parser.add_argument("--chroma-dir", default=str(DEFAULT_CHROMA_DIR), help="Path to Chroma directory")
    parser.add_argument("--collection", default=CHROMA_COLLECTION, help="Collection name")
    parser.add_argument("--query", default="probable cause", help="Query to test")
    parser.add_argument("--k", type=int, default=5, help="Top-k results to show")
    args = parser.parse_args()

    chroma_dir = Path(args.chroma_dir)
    client = _create_client(chroma_dir)
    _print_collections(client)

    collection = get_or_create_collection(client, name=args.collection)
    try:
        meta = collection.metadata or {}
    except Exception:
        meta = {}
    if meta.get(CHROMA_METADATA_EMBEDDING_KEY) and meta.get(CHROMA_METADATA_EMBEDDING_KEY) != EMBEDDING_MODEL_ID:
        print("Warning: embedding model mismatch", meta.get(CHROMA_METADATA_EMBEDDING_KEY), "!=", EMBEDDING_MODEL_ID)

    count = 0
    try:
        count = collection.count()
    except Exception:
        count = 0
    print(f"Collection '{args.collection}' count:", count)
    if count == 0:
        raise SystemExit("Chroma collection is empty. Ingestion likely failed or used a different collection name.")

    try:
        model = SentenceTransformer(EMBEDDING_MODEL_ID)
        query_embedding = model.encode([args.query]).tolist()[0]
        result = collection.query(
            query_embeddings=[query_embedding],
            n_results=args.k,
            include=["metadatas", "documents"],
        )
    except Exception as exc:
        raise SystemExit(f"Query failed: {exc}")

    ids = result.get("ids", [[]])[0]
    metas = result.get("metadatas", [[]])[0]
    print("Top results:")
    for idx, doc_id in enumerate(ids):
        meta = metas[idx] if idx < len(metas) else {}
        summary = {k: meta.get(k) for k in ("title", "path", "source_type", "chunk_index") if meta.get(k) is not None}
        print(f"  {idx+1}. {doc_id} -> {json.dumps(summary, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
