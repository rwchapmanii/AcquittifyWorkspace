from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable, List, Optional

import chromadb
from sentence_transformers import SentenceTransformer
import psycopg
from psycopg.rows import dict_row

from acquittify.chunking import chunk_text, chunk_text_with_offsets
from acquittify.chroma_utils import get_or_create_collection, upsert_or_add
from acquittify.config import CHROMA_COLLECTION, EMBEDDING_MODEL_ID
from acquittify.ingest.metadata_utils import augment_chunk_metadata

from document_ingestion_backend import (
    extract_pdf_text,
    infer_source_type,
    summarize_and_extract_metadata,
    analyze_chunk,
)
from ingestion_agent.sources.courtlistener import CourtListenerClient
from ingestion_agent.config import Settings as CourtListenerSettings
from ingestion_agent.parsers.cleaner import clean_text
from ingestion_agent.utils.text import strip_html


def _clean_chroma_metadata(meta: dict) -> dict:
    cleaned = {}
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


def _chunk_with_optional_offsets(text: str):
    if os.getenv("ACQ_CHUNK_WITH_OFFSETS") == "1":
        payloads = chunk_text_with_offsets(text)
        chunks = [p.get("text", "") for p in payloads]
        return chunks, payloads
    return chunk_text(text), None


def _embed_texts(model: SentenceTransformer, texts: List[str]) -> Optional[List[List[float]]]:
    try:
        return model.encode(texts, batch_size=64, show_progress_bar=False).tolist()
    except Exception:
        return None


def _upsert_chunks(collection, chunks: List[str], metadatas: List[dict], embeddings: Optional[List[List[float]]]) -> None:
    ids = []
    for meta in metadatas:
        doc_id = meta.get("doc_id") or meta.get("id") or meta.get("path") or "chunk"
        chunk_index = meta.get("chunk_index")
        ids.append(f"{doc_id}_{chunk_index}" if chunk_index is not None else str(doc_id))
    batch_size = 500
    for i in range(0, len(ids), batch_size):
        end = min(i + batch_size, len(ids))
        upsert_or_add(
            collection,
            ids=ids[i:end],
            documents=chunks[i:end],
            embeddings=embeddings[i:end] if embeddings else None,
            metadatas=metadatas[i:end],
        )


def ingest_pdf_paths(
    pdf_paths: Iterable[Path],
    chroma_dir: Path,
    use_taxonomy: bool = True,
    skip_summary: bool = False,
) -> None:
    model = SentenceTransformer(EMBEDDING_MODEL_ID)
    client = chromadb.PersistentClient(path=str(chroma_dir))
    collection = get_or_create_collection(client, name=CHROMA_COLLECTION)

    for pdf in pdf_paths:
        text = extract_pdf_text(pdf)
        if not text:
            continue
        chunks, offsets = _chunk_with_optional_offsets(text)
        if not chunks:
            continue
        source_type = infer_source_type(pdf)
        title = pdf.stem.replace("_", " ")
        document_type = source_type or "Corpus"
        case_name = "Corpus"

        if skip_summary:
            doc_metadata = {
                "document_type": document_type,
                "case": case_name,
                "case_name": case_name,
            }
        else:
            _, doc_metadata = summarize_and_extract_metadata(text, document_type, case_name)

        embeddings = _embed_texts(model, chunks)

        taxonomy_seed = "\n\n".join(chunks[:3])
        doc_taxonomy = analyze_chunk(taxonomy_seed) if use_taxonomy and taxonomy_seed else {}

        metadatas = []
        for i, chunk in enumerate(chunks):
            meta = dict(doc_metadata)
            meta.update({
                "title": title,
                "source_type": source_type,
                "document_type": document_type,
                "case": case_name,
                "case_name": case_name,
                "path": str(pdf),
                "doc_id": pdf.stem,
                "chunk_index": i,
            })
            if offsets and i < len(offsets):
                meta["char_start"] = offsets[i].get("char_start")
                meta["char_end"] = offsets[i].get("char_end")
            if doc_taxonomy:
                meta["taxonomy"] = json.dumps(doc_taxonomy)
            meta = augment_chunk_metadata(meta, chunk)
            metadatas.append(_clean_chroma_metadata(meta))

        _upsert_chunks(collection, chunks, metadatas, embeddings)


def ingest_local_corpus(
    raw_dir: Path,
    chroma_dir: Path,
    use_taxonomy: bool = True,
    skip_summary: bool = False,
) -> None:
    pdfs = list(raw_dir.rglob("*.pdf"))
    ingest_pdf_paths(pdfs, chroma_dir, use_taxonomy=use_taxonomy, skip_summary=skip_summary)


def _choose_text(record: dict) -> str:
    for key in ("plain_text", "html_with_citations", "html", "opinion_text"):
        value = record.get(key)
        if value:
            return value
    return ""


def _normalize_text(raw_text: str) -> str:
    return clean_text(strip_html(raw_text))


def ingest_courtlistener(
    chroma_dir: Path,
    since: Optional[str],
    max_pages: int,
    use_taxonomy: bool = True,
) -> None:
    model = SentenceTransformer(EMBEDDING_MODEL_ID)
    client = chromadb.PersistentClient(path=str(chroma_dir))
    collection = get_or_create_collection(client, name=CHROMA_COLLECTION)

    settings = CourtListenerSettings()
    client_api = CourtListenerClient(settings)

    def process_records(records: Iterable[dict], source_type: str):
        for record in records:
            raw_text = _choose_text(record)
            if not raw_text:
                continue
            normalized = _normalize_text(raw_text)
            chunks, offsets = _chunk_with_optional_offsets(normalized)
            if not chunks:
                continue

            title = record.get("case_name") or record.get("case") or record.get("short_name") or source_type
            meta_base = {
                "title": title,
                "source_type": source_type,
                "document_type": source_type,
                "doc_id": str(record.get("id", "")),
                "court": record.get("court") or record.get("court_id"),
                "date_filed": record.get("date_filed"),
                "citation": record.get("citation") or record.get("cite"),
                "document_citation": record.get("citation") or record.get("cite"),
                "docket_number": record.get("docket_number") or record.get("docket"),
                "url": record.get("absolute_url") or record.get("resource_uri"),
                "path": record.get("absolute_url") or record.get("resource_uri"),
            }

            embeddings = _embed_texts(model, chunks)
            metadatas = []
            for i, chunk in enumerate(chunks):
                meta = dict(meta_base)
                meta["chunk_index"] = i
                if offsets and i < len(offsets):
                    meta["char_start"] = offsets[i].get("char_start")
                    meta["char_end"] = offsets[i].get("char_end")
                if use_taxonomy:
                    taxonomy = analyze_chunk(chunk)
                    if taxonomy:
                        meta["taxonomy"] = json.dumps(taxonomy)
                meta = augment_chunk_metadata(meta, chunk)
                metadatas.append(_clean_chroma_metadata(meta))
            _upsert_chunks(collection, chunks, metadatas, embeddings)

    process_records(client_api.iter_opinions(since=since, max_pages=max_pages), "CourtListener Opinion")
    process_records(client_api.iter_recap_filings(since=since, max_pages=max_pages), "CourtListener RECAP")


def ingest_courtlistener_db(
    chroma_dir: Path,
    dsn: str,
    since: Optional[str] = None,
    limit: Optional[int] = None,
    use_taxonomy: bool = True,
) -> None:
    model = SentenceTransformer(EMBEDDING_MODEL_ID)
    client = chromadb.PersistentClient(path=str(chroma_dir))
    collection = get_or_create_collection(client, name=CHROMA_COLLECTION)

    where_clause = ""
    params: List = []
    if since:
        where_clause = "WHERE COALESCE(oc.date_filed, o.date_created) >= %s"
        params.append(since)

    limit_clause = ""
    if limit:
        limit_clause = "LIMIT %s"
        params.append(limit)

    sql = f"""
        SELECT
            o.id,
            o.plain_text,
            o.opinion_text,
            o.html_with_citations,
            o.html,
            o.date_created,
            o.record_json,
            oc.date_filed,
            oc.court_id
        FROM raw.opinions o
        LEFT JOIN raw.opinion_clusters oc ON oc.id = o.cluster_id
        {where_clause}
        ORDER BY o.id
        {limit_clause}
    """

    with psycopg.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    if not rows:
        return

    for row in rows:
        record_json = row.get("record_json") or {}
        record = {
            "id": row.get("id"),
            "plain_text": row.get("plain_text"),
            "opinion_text": row.get("opinion_text"),
            "html_with_citations": row.get("html_with_citations"),
            "html": row.get("html"),
            "date_filed": row.get("date_filed"),
            "court_id": row.get("court_id"),
            "citation": record_json.get("citation") or record_json.get("cite"),
            "docket_number": record_json.get("docket_number") or record_json.get("docket"),
            "absolute_url": record_json.get("absolute_url") or record_json.get("resource_uri"),
            "case_name": record_json.get("case_name") or record_json.get("case") or record_json.get("caption"),
        }

        raw_text = _choose_text(record)
        if not raw_text:
            continue

        normalized = _normalize_text(raw_text)
        chunks, offsets = _chunk_with_optional_offsets(normalized)
        if not chunks:
            continue

        title = record.get("case_name") or f"Opinion {record.get('id')}"
        meta_base = {
            "title": title,
            "source_type": "CourtListener Opinion",
            "document_type": "CourtListener Opinion",
            "doc_id": str(record.get("id", "")),
            "court": record.get("court_id"),
            "date_filed": record.get("date_filed"),
            "citation": record.get("citation"),
            "document_citation": record.get("citation"),
            "docket_number": record.get("docket_number"),
            "url": record.get("absolute_url"),
            "path": record.get("absolute_url"),
        }

        embeddings = _embed_texts(model, chunks)
        metadatas = []
        for i, chunk in enumerate(chunks):
            meta = dict(meta_base)
            meta["chunk_index"] = i
            if offsets and i < len(offsets):
                meta["char_start"] = offsets[i].get("char_start")
                meta["char_end"] = offsets[i].get("char_end")
            if use_taxonomy:
                taxonomy = analyze_chunk(chunk)
                if taxonomy:
                    meta["taxonomy"] = json.dumps(taxonomy)
            meta = augment_chunk_metadata(meta, chunk)
            metadatas.append(_clean_chroma_metadata(meta))

        _upsert_chunks(collection, chunks, metadatas, embeddings)
