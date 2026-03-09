#!/usr/bin/env python3
"""Autonomous CourtListener opinion ingestion with logging for Admin UI."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import chromadb
from sentence_transformers import SentenceTransformer

from acquittify.chunking import chunk_text
from acquittify.chroma_utils import get_or_create_collection, upsert_or_add
from acquittify.config import CHROMA_COLLECTION, EMBEDDING_MODEL_ID
from acquittify.ingest.metadata_utils import augment_chunk_metadata
from document_ingestion_backend import analyze_chunk
from ingestion_agent.config import Settings as CourtListenerSettings
from ingestion_agent.parsers.cleaner import clean_text
from ingestion_agent.sources.courtlistener import CourtListenerClient
from ingestion_agent.utils.text import strip_html


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_today() -> str:
    return date.today().isoformat()


def _load_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))


def _append_event(path: Path, event: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


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


def _embed_texts(model: SentenceTransformer, texts: list[str]) -> Optional[list[list[float]]]:
    try:
        return model.encode(texts, batch_size=64, show_progress_bar=False).tolist()
    except Exception:
        return None


def _upsert_chunks(collection, chunks: list[str], metadatas: list[dict], embeddings: Optional[list[list[float]]]) -> None:
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


def _choose_text(record: dict) -> str:
    for key in ("plain_text", "html_with_citations", "html", "opinion_text"):
        value = record.get(key)
        if value:
            return value
    return ""


def _normalize_text(raw_text: str) -> str:
    return clean_text(strip_html(raw_text))


def _iter_opinions(client_api: CourtListenerClient, since: Optional[str], max_pages: int) -> Iterable[dict]:
    return client_api.iter_opinions(since=since, max_pages=max_pages)


def ingest_opinions_once(
    chroma_dir: Path,
    since: Optional[str],
    max_pages: int,
    use_taxonomy: bool,
    log_path: Path,
) -> dict:
    started_at = _utc_now_iso()
    model = SentenceTransformer(EMBEDDING_MODEL_ID)
    client = chromadb.PersistentClient(path=str(chroma_dir))
    collection = get_or_create_collection(client, name=CHROMA_COLLECTION)

    settings = CourtListenerSettings()
    if not settings.api_token:
        raise RuntimeError("COURTLISTENER_API_TOKEN is not set; API access denied.")
    client_api = CourtListenerClient(settings)

    counts = {
        "total_records": 0,
        "embedded_docs": 0,
        "skipped_no_text": 0,
        "failed_docs": 0,
        "embedded_chunks": 0,
    }

    for record in _iter_opinions(client_api, since=since, max_pages=max_pages):
        counts["total_records"] += 1
        doc_id = str(record.get("id", ""))
        title = record.get("case_name") or record.get("case") or record.get("short_name") or "CourtListener Opinion"
        event = {
            "event": "document",
            "recorded_at": _utc_now_iso(),
            "doc_id": doc_id,
            "title": title,
            "court": record.get("court") or record.get("court_id"),
            "date_filed": record.get("date_filed"),
            "citation": record.get("citation") or record.get("cite"),
            "docket_number": record.get("docket_number") or record.get("docket"),
            "url": record.get("absolute_url") or record.get("resource_uri"),
        }
        try:
            raw_text = _choose_text(record)
            if not raw_text:
                counts["skipped_no_text"] += 1
                event["status"] = "skipped_no_text"
                _append_event(log_path, event)
                continue

            normalized = _normalize_text(raw_text)
            chunks = chunk_text(normalized)
            if not chunks:
                counts["skipped_no_text"] += 1
                event["status"] = "skipped_empty_chunks"
                _append_event(log_path, event)
                continue

            meta_base = {
                "title": title,
                "source_type": "CourtListener Opinion",
                "document_type": "CourtListener Opinion",
                "doc_id": doc_id,
                "court": record.get("court") or record.get("court_id"),
                "date_filed": record.get("date_filed"),
                "citation": record.get("citation") or record.get("cite"),
                "docket_number": record.get("docket_number") or record.get("docket"),
                "url": record.get("absolute_url") or record.get("resource_uri"),
                "path": record.get("absolute_url") or record.get("resource_uri"),
            }

            embeddings = _embed_texts(model, chunks)
            metadatas = []
            for i, chunk in enumerate(chunks):
                meta = dict(meta_base)
                meta["chunk_index"] = i
                if use_taxonomy:
                    taxonomy = analyze_chunk(chunk)
                    if taxonomy:
                        meta["taxonomy"] = json.dumps(taxonomy)
                meta = augment_chunk_metadata(meta, chunk)
                metadatas.append(_clean_chroma_metadata(meta))

            _upsert_chunks(collection, chunks, metadatas, embeddings)
            counts["embedded_docs"] += 1
            counts["embedded_chunks"] += len(chunks)
            event["status"] = "embedded"
            event["chunks"] = len(chunks)
            _append_event(log_path, event)
        except Exception as exc:
            counts["failed_docs"] += 1
            event["status"] = "error"
            event["error"] = str(exc)
            _append_event(log_path, event)

    ended_at = _utc_now_iso()
    status = "ok" if counts["failed_docs"] == 0 else "partial"
    summary = {
        "event": "run_summary",
        "recorded_at": ended_at,
        "started_at": started_at,
        "ended_at": ended_at,
        "since": since,
        "status": status,
        **counts,
    }
    _append_event(log_path, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Autonomous CourtListener opinion ingestion")
    parser.add_argument("--once", action="store_true", help="Run a single ingest cycle and exit")
    parser.add_argument("--interval", type=int, default=int(os.getenv("COURTLISTENER_POLL_SECONDS", "900")))
    parser.add_argument("--since", default=os.getenv("COURTLISTENER_OPINION_SINCE"))
    parser.add_argument("--max-pages", type=int, default=int(os.getenv("COURTLISTENER_API_MAX_PAGES", "5")))
    parser.add_argument("--chroma-dir", default=os.getenv("CHROMA_DIR", "Corpus/Chroma"))
    parser.add_argument("--no-taxonomy", action="store_true", help="Disable taxonomy tagging")
    parser.add_argument(
        "--state-path",
        default=os.getenv("COURTLISTENER_OPINION_STATE_PATH", "Casefiles/courtlistener_opinion_state.json"),
    )
    parser.add_argument(
        "--log-path",
        default=os.getenv("COURTLISTENER_OPINION_LOG_PATH", "Casefiles/courtlistener_ingest_log.jsonl"),
    )
    args = parser.parse_args()

    state_path = Path(args.state_path)
    log_path = Path(args.log_path)
    chroma_dir = Path(args.chroma_dir)

    while True:
        state = _load_state(state_path)
        last_success = state.get("last_successful_date")
        since = last_success or args.since or _utc_today()

        summary = None
        try:
            summary = ingest_opinions_once(
                chroma_dir=chroma_dir,
                since=since,
                max_pages=args.max_pages,
                use_taxonomy=not args.no_taxonomy,
                log_path=log_path,
            )
            state["last_successful_date"] = _utc_today()
            state["last_status"] = summary.get("status") if summary else "unknown"
            state["last_run_at"] = _utc_now_iso()
            _save_state(state_path, state)
        except Exception as exc:
            error_event = {
                "event": "run_summary",
                "recorded_at": _utc_now_iso(),
                "started_at": _utc_now_iso(),
                "ended_at": _utc_now_iso(),
                "since": since,
                "status": "error",
                "error": str(exc),
            }
            _append_event(log_path, error_event)

        if args.once:
            break
        time.sleep(max(60, args.interval))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
