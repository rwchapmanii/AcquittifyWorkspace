#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import chromadb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from acquittify.config import CHROMA_COLLECTION
from acquittify.ingest.metadata_utils import augment_chunk_metadata


def _clean_chroma_metadata(meta: Dict[str, Any]) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {}
    for key, value in (meta or {}).items():
        if value is None:
            continue
        if isinstance(value, (list, dict)):
            try:
                value = json.dumps(value, ensure_ascii=False)
            except Exception:
                continue
        if isinstance(value, (str, int, float, bool)):
            cleaned[key] = value
    return cleaned


def _get_collection(chroma_dir: str, name: Optional[str]) -> Any:
    client = chromadb.PersistentClient(path=chroma_dir)
    return client.get_or_create_collection(name=name or CHROMA_COLLECTION)


def _maybe_infer_taxonomy(text: str) -> Optional[dict]:
    if not text:
        return None
    try:
        from taxonomy_embedding_agent import analyze_chunk
    except Exception:
        return None
    try:
        return analyze_chunk(text)
    except Exception:
        return None


def _should_update(existing: Dict[str, Any], updated: Dict[str, Any]) -> bool:
    return existing != updated


def enrich_collection(
    chroma_dir: str,
    collection_name: Optional[str],
    batch_size: int,
    limit: Optional[int],
    offset: int,
    infer_taxonomy: bool,
    dry_run: bool,
) -> Tuple[int, int, int]:
    collection = _get_collection(chroma_dir, collection_name)
    total = collection.count()
    start = max(offset, 0)
    end = min(total, start + limit) if limit else total

    processed = 0
    updated = 0
    errors = 0

    for batch_start in range(start, end, batch_size):
        batch_limit = min(batch_size, end - batch_start)
        try:
            res = collection.get(
                limit=batch_limit,
                offset=batch_start,
                include=["metadatas", "documents"],
            )
        except Exception as exc:
            print(f"batch {batch_start} failed: {exc}")
            errors += batch_limit
            continue

        ids = res.get("ids") or []
        metadatas = res.get("metadatas") or []
        documents = res.get("documents") or []

        update_ids: List[str] = []
        update_metas: List[Dict[str, Any]] = []
        update_docs: List[str] = []

        for idx, doc_id in enumerate(ids):
            meta = metadatas[idx] if idx < len(metadatas) and isinstance(metadatas[idx], dict) else {}
            doc = documents[idx] if idx < len(documents) else ""
            processed += 1

            if doc:
                new_meta = augment_chunk_metadata(meta, doc)
                taxonomy_value = meta.get("taxonomy")
                empty_taxonomy = False
                if taxonomy_value is None:
                    empty_taxonomy = True
                elif isinstance(taxonomy_value, str) and taxonomy_value.strip() in {"", "{}", "null", "[]"}:
                    empty_taxonomy = True
                if infer_taxonomy and empty_taxonomy:
                    taxonomy = _maybe_infer_taxonomy(doc)
                    if taxonomy:
                        new_meta["taxonomy"] = json.dumps(taxonomy, ensure_ascii=False)
            else:
                new_meta = dict(meta)

            cleaned_existing = _clean_chroma_metadata(meta)
            cleaned_new = _clean_chroma_metadata(new_meta)

            if _should_update(cleaned_existing, cleaned_new):
                update_ids.append(doc_id)
                update_metas.append(cleaned_new)
                update_docs.append(doc)

        if not update_ids:
            continue

        if dry_run:
            updated += len(update_ids)
            continue

        try:
            collection.update(ids=update_ids, metadatas=update_metas)
            updated += len(update_ids)
        except Exception:
            try:
                collection.upsert(ids=update_ids, documents=update_docs, metadatas=update_metas)
                updated += len(update_ids)
            except Exception as exc:
                errors += len(update_ids)
                print(f"update failed for batch {batch_start}: {exc}")

    return processed, updated, errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich existing Chroma metadata without re-embedding.")
    parser.add_argument("--chroma-dir", default=os.getenv("CHROMA_DIR", "Corpus/Chroma"))
    parser.add_argument("--collection", default=None)
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--infer-taxonomy", action="store_true", help="Use analyze_chunk to fill missing taxonomy")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    processed, updated, errors = enrich_collection(
        chroma_dir=args.chroma_dir,
        collection_name=args.collection,
        batch_size=args.batch_size,
        limit=args.limit,
        offset=args.offset,
        infer_taxonomy=args.infer_taxonomy,
        dry_run=args.dry_run,
    )

    print(f"processed={processed} updated={updated} errors={errors}")


if __name__ == "__main__":
    main()
