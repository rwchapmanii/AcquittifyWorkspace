#!/usr/bin/env python3
"""Ingest CAP JSONL shards into Chroma with Acquittify chunking + metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Set, TextIO

import chromadb
import requests

from acquittify.config import CHROMA_COLLECTION, EMBEDDING_MODEL_ID
from acquittify.chroma_utils import get_or_create_collection, upsert_or_add
from acquittify.ingest.metadata_utils import augment_chunk_metadata
from acquittify.metadata_extract import normalize_citations
from document_ingestion_backend import (
    _clean_metadata,
    _chunk_with_optional_offsets,
    _encode_embeddings,
)

try:
    from taxonomy_embedding_agent import analyze_chunk, build_metadata
except Exception:
    from document_ingestion_backend import analyze_chunk, build_metadata

CASE_CLASSIFY_URL = os.getenv(
    "ACQUITTIFY_CASE_CLASSIFY_URL",
    os.getenv("ACQUITTIFY_INGESTION_OLLAMA_URL", "http://localhost:11434/api/chat"),
)
CASE_CLASSIFY_MODEL = os.getenv(
    "ACQUITTIFY_CASE_CLASSIFY_MODEL",
    os.getenv("ACQUITTIFY_INGESTION_MODEL", "qwen-acquittify-ingestion14b"),
)
CASE_CLASSIFY_MODE = os.getenv("ACQUITTIFY_CASE_CLASSIFY_MODE", "llm").lower()


def _iter_shards(shards_dir: Path) -> Iterator[Path]:
    for path in sorted(shards_dir.glob("cases_*.jsonl")):
        yield path


def _iter_records(path: Path) -> Iterator[dict]:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                yield payload


def _doc_id(record: dict) -> str:
    cap_id = record.get("cap_id")
    if cap_id:
        return f"cap_{cap_id}"
    fallback = json.dumps(record, sort_keys=True, default=str).encode("utf-8")
    return f"cap_{hashlib.sha256(fallback).hexdigest()[:16]}"


def _extract_citation_strings(citations) -> list[str]:
    items: list[str] = []
    if isinstance(citations, list):
        for cite in citations:
            value = None
            if isinstance(cite, dict):
                value = cite.get("cite") or cite.get("citation")
            elif isinstance(cite, str):
                value = cite
            else:
                value = str(cite)
            if value:
                items.append(str(value))
    elif isinstance(citations, dict):
        value = citations.get("cite") or citations.get("citation")
        if value:
            items.append(str(value))
    elif isinstance(citations, str):
        items.append(citations)
    return [item for item in (s.strip() for s in items) if item]


def _decision_year(decision_date: str | None) -> str | None:
    if not decision_date:
        return None
    text = str(decision_date).strip()
    if len(text) >= 4 and text[:4].isdigit():
        return text[:4]
    return None


def _decision_sort_key(decision_date: str | None) -> tuple[int, int, int]:
    if not decision_date:
        return (0, 0, 0)
    text = str(decision_date).strip()
    match = re.match(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?", text)
    if not match:
        return (0, 0, 0)
    year = int(match.group(1))
    month = int(match.group(2)) if match.group(2) else 0
    day = int(match.group(3)) if match.group(3) else 0
    return (year, month, day)


def _format_document_citation(case_name: str, cite: str, year: str | None, page: str | None) -> str:
    base = f"{case_name} {cite}" if case_name else cite
    if page:
        base = f"{base}, {page}"
    if year:
        base = f"{base} ({year})"
    return base


def _normalize_court(value) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("name") or value.get("name_abbreviation") or value.get("slug") or value.get("id")
    return None


def _load_seen_doc_ids(log_path: Path | None) -> Set[str]:
    if not log_path or not log_path.exists():
        return set()
    seen: Set[str] = set()
    with log_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            doc_id = payload.get("doc_id")
            if isinstance(doc_id, str) and doc_id:
                seen.add(doc_id)
    return seen


def _heuristic_case_type(text: str) -> tuple[str, str]:
    lower = text.lower()
    if "2255" in lower or "§ 2255" in lower or "habeas" in lower:
        return "quasi_criminal", "mentions 2255/habeas relief"
    if re.search(r"\b(18|21)\s*u\.s\.c\b", lower) or "indict" in lower or "criminal" in lower:
        return "criminal", "mentions criminal statute or indictment terminology"
    if "misdemeanor" in lower or "felony" in lower or "sentenc" in lower:
        return "criminal", "mentions criminal offense or sentencing"
    return "non_criminal", "no criminal statute or quasi-criminal indicators found"


def classify_case_type(
    case_name: str | None,
    citations: list[str] | None,
    opinion_text: str,
    scan_chars: int,
    mode: str | None = None,
) -> dict:
    mode = (mode or CASE_CLASSIFY_MODE).lower()
    snippet = (opinion_text or "").strip()[: max(scan_chars, 200)]
    if mode == "heuristic":
        case_type, reason = _heuristic_case_type(snippet)
        return {"case_type": case_type, "reason": reason, "method": "heuristic"}

    prompt = f"""
You are classifying legal cases for ingestion.

Definitions:
- criminal: alleges violation of a criminal statute.
- quasi_criminal: alleges violation of statutes or regulations with administrative punishments and relief requested under 28 U.S.C. § 2255.
- non_criminal: none of the above.
-Evidence: cases involving a rule of evidence do not by themselves make a case criminal or quasi_criminal but should be processed. 

Return ONLY JSON with fields: case_type (criminal|quasi_criminal|non_criminal) and reason.

Case name: {case_name or "unknown"}
Citations: {citations or []}

Text snippet:
{snippet}
"""
    try:
        payload = {
            "model": CASE_CLASSIFY_MODEL,
            "messages": [
                {"role": "system", "content": "Return only valid JSON. No prose."},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {"temperature": 0},
        }
        response = requests.post(CASE_CLASSIFY_URL, json=payload, timeout=60)
        if response.status_code != 200:
            raise RuntimeError(f"LLM error: {response.text}")
        result = response.json()
        content = result.get("message", {}).get("content", "{}").strip()
        parsed = json.loads(content)
        case_type = parsed.get("case_type")
        reason = parsed.get("reason")
        if case_type not in {"criminal", "quasi_criminal", "non_criminal"}:
            raise ValueError("Invalid case_type")
        return {"case_type": case_type, "reason": reason or "", "method": "llm"}
    except Exception:
        case_type, reason = _heuristic_case_type(snippet)
        return {"case_type": case_type, "reason": reason, "method": "heuristic_fallback"}


def _build_meta_base(record: dict, doc_id: str) -> dict:
    case_name = record.get("case_name") or record.get("title") or "CAP Case"
    citation_strings = _extract_citation_strings(record.get("citations"))
    year = _decision_year(record.get("decision_date"))
    page = record.get("page")
    document_citation = None
    if citation_strings:
        document_citation = _format_document_citation(case_name, citation_strings[0], year, page)
    return {
        "doc_id": doc_id,
        "source": record.get("source") or "cap-static-case-law",
        "source_type": "CAP Static Case Law",
        "document_type": "Case Law",
        "title": case_name,
        "case_name": case_name,
        "case": case_name,
        "court": _normalize_court(record.get("court")),
        "decision_date": record.get("decision_date"),
        "date": record.get("decision_date"),
        "docket_number": record.get("docket_number"),
        "citations": citation_strings,
        "bluebook_citations": normalize_citations(citation_strings) if citation_strings else [],
        "document_citation": document_citation,
        "reporter_slug": record.get("reporter_slug"),
        "volume": record.get("volume"),
        "page": record.get("page"),
        "cap_id": record.get("cap_id"),
        "opinion_text_type": record.get("opinion_text_type"),
        "download_url": record.get("download_url"),
        "sha256_raw_file": record.get("sha256_raw_file"),
        "path": record.get("download_url"),
        "file_hash": record.get("sha256_raw_file"),
    }


def ingest_shards(
    shards_dir: Path,
    chroma_dir: Path,
    limit: int | None = None,
    slugs: list[str] | None = None,
    min_year: int | None = None,
    max_year: int | None = None,
    court_contains: list[str] | None = None,
    sort_desc: bool = False,
    inspect: bool = False,
    inspect_records: int | None = 1,
    inspect_chunks: int = 2,
    inspect_output: Path | None = None,
    inspect_no_text: bool = False,
    filter_criminal: bool = False,
    case_scan_chars: int = 6000,
    case_classify_mode: str | None = None,
    pause_file: Path | None = None,
    pause_check_interval: float = 5.0,
    throttle_seconds: float = 0.0,
    resume_log: Path | None = None,
    progress_log: Path | None = None,
    progress_interval: int = 500,
    stage_name: str | None = None,
) -> dict:
    client = chromadb.PersistentClient(path=str(chroma_dir))
    collection = get_or_create_collection(client, name=CHROMA_COLLECTION)

    total_records = 0
    total_chunks = 0
    skipped = 0
    skipped_non_criminal = 0
    skipped_seen = 0

    seen_doc_ids = _load_seen_doc_ids(resume_log)

    slug_order = [s.lower() for s in slugs] if slugs else None
    court_tokens = [token.lower() for token in (court_contains or []) if token]
    inspect_handle: TextIO | None = None
    inspected_records = 0
    progress_handle: TextIO | None = None
    last_progress_count = 0

    if inspect and inspect_records is not None and inspect_records < 1:
        inspect_records = 1
    if inspect and inspect_chunks < 1:
        inspect_chunks = 1

    if inspect:
        if inspect_output is None:
            inspect_output = Path("reports") / "ingest_CAP_log.jsonl"
        inspect_output.parent.mkdir(parents=True, exist_ok=True)
        inspect_handle = inspect_output.open("a", encoding="utf-8", buffering=1)

    if progress_log is not None and progress_interval != 0:
        progress_log.parent.mkdir(parents=True, exist_ok=True)
        progress_handle = progress_log.open("a", encoding="utf-8", buffering=1)

    def _emit_inspect(payload: dict) -> None:
        line = json.dumps(payload, ensure_ascii=False)
        if inspect_handle:
            inspect_handle.write(line + "\n")
            inspect_handle.flush()
        else:
            print(line)

    def _emit_progress(force: bool = False) -> None:
        nonlocal last_progress_count
        if not progress_handle:
            return
        if not force and progress_interval <= 0:
            return
        if not force and (total_records - last_progress_count) < progress_interval:
            return
        last_progress_count = total_records
        payload = {
            "ts": time.time(),
            "stage": stage_name or "default",
            "records": total_records,
            "chunks": total_chunks,
            "skipped": skipped,
            "skipped_non_criminal": skipped_non_criminal,
            "skipped_seen": skipped_seen,
        }
        progress_handle.write(json.dumps(payload) + "\n")
        progress_handle.flush()

    def _wait_if_paused() -> None:
        if not pause_file:
            return
        while pause_file.exists():
            time.sleep(pause_check_interval)

    def _throttle() -> None:
        if throttle_seconds > 0:
            time.sleep(throttle_seconds)

    def _matches_slug(record: dict) -> bool:
        if not slug_order:
            return True
        reporter = record.get("reporter_slug")
        return isinstance(reporter, str) and reporter.lower() in slug_order

    def _matches_year(record: dict) -> bool:
        if min_year is None and max_year is None:
            return True
        year_text = _decision_year(record.get("decision_date"))
        if not year_text or not year_text.isdigit():
            return False
        year = int(year_text)
        if min_year is not None and year < min_year:
            return False
        if max_year is not None and year > max_year:
            return False
        return True

    def _matches_court(record: dict) -> bool:
        if not court_tokens:
            return True
        court_value = _normalize_court(record.get("court"))
        if not court_value:
            return False
        lower = str(court_value).lower()
        return any(token in lower for token in court_tokens)

    def _matches_record(record: dict) -> bool:
        return _matches_slug(record) and _matches_year(record) and _matches_court(record)

    def _ingest_record(record: dict) -> None:
        nonlocal total_records, total_chunks, skipped, inspected_records, skipped_non_criminal, skipped_seen
        if limit is not None and total_records >= limit:
            return

        _wait_if_paused()
        _throttle()

        text = record.get("opinion_text") or ""
        if not text.strip():
            skipped += 1
            total_records += 1
            return

        doc_id = _doc_id(record)
        if doc_id in seen_doc_ids:
            skipped_seen += 1
            total_records += 1
            return
        meta_base = _build_meta_base(record, doc_id)
        case_name = meta_base.get("case_name")
        classification = classify_case_type(
            case_name,
            meta_base.get("citations") or [],
            text,
            case_scan_chars,
            mode=case_classify_mode,
        )
        meta_base["case_type"] = classification.get("case_type")
        meta_base["case_type_reason"] = classification.get("reason")
        meta_base["case_type_method"] = classification.get("method")

        if filter_criminal and classification.get("case_type") == "non_criminal":
            if inspect:
                _emit_inspect(
                    {
                        "doc_id": doc_id,
                        "record_index": total_records,
                        "case_name": case_name,
                        "case_type": classification.get("case_type"),
                        "case_type_reason": classification.get("reason"),
                        "case_type_method": classification.get("method"),
                        "decision": "skipped_non_criminal",
                        "metadata": _clean_metadata(meta_base),
                    }
                )
            skipped_non_criminal += 1
            total_records += 1
            return

        chunks, offsets = _chunk_with_optional_offsets(text)
        if not chunks:
            skipped += 1
            total_records += 1
            return

        _wait_if_paused()
        _throttle()

        embeddings = _encode_embeddings(chunks)
        if embeddings is None:
            raise RuntimeError("Embedding model unavailable; cannot store vectors.")

        ids: List[str] = []
        metadatas: List[dict] = []
        should_inspect = inspect and (inspect_records is None or inspected_records < inspect_records)
        inspected_chunks = 0
        for i, chunk in enumerate(chunks):
            taxonomy = analyze_chunk(chunk)
            meta = dict(meta_base)
            meta.update(build_metadata(doc_id, meta_base.get("source", "cap"), i, taxonomy))
            if offsets and i < len(offsets):
                meta["char_start"] = offsets[i].get("char_start")
                meta["char_end"] = offsets[i].get("char_end")
            meta = augment_chunk_metadata(meta, chunk)
            if not meta.get("citations"):
                cap_citations = meta_base.get("citations") or []
                meta["citations"] = cap_citations
                meta["bluebook_citations"] = meta_base.get("bluebook_citations") or []
                meta["citation_count"] = len(cap_citations)
                meta["bluebook_citation_count"] = len(meta.get("bluebook_citations") or [])
                if not meta.get("document_citation") and cap_citations:
                    meta["document_citation"] = meta_base.get("document_citation") or cap_citations[0]
                    meta["case_citation_method"] = "cap_metadata"
                    meta["case_citation_is_synthetic"] = False
            clean_meta = _clean_metadata(meta)
            if should_inspect and inspected_chunks < inspect_chunks:
                payload = {
                    "doc_id": doc_id,
                    "record_index": total_records,
                    "chunk_index": i,
                    "chunk_id": f"{doc_id}_{i}",
                    "chunk_char_start": clean_meta.get("char_start"),
                    "chunk_char_end": clean_meta.get("char_end"),
                    "case_type": classification.get("case_type"),
                    "case_type_reason": classification.get("reason"),
                    "case_type_method": classification.get("method"),
                    "citations": clean_meta.get("citations"),
                    "bluebook_citations": clean_meta.get("bluebook_citations"),
                    "document_citation": clean_meta.get("document_citation"),
                    "embedding": {
                        "collection": CHROMA_COLLECTION,
                        "chroma_dir": str(chroma_dir),
                        "embedding_model_id": EMBEDDING_MODEL_ID,
                    },
                    "metadata": clean_meta,
                }
                if not inspect_no_text:
                    payload["chunk_text"] = chunk
                _emit_inspect(payload)
                inspected_chunks += 1
            metadatas.append(clean_meta)
            ids.append(f"{doc_id}_{i}")

        upsert_or_add(
            collection,
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        seen_doc_ids.add(doc_id)
        total_records += 1
        total_chunks += len(chunks)
        if should_inspect:
            inspected_records += 1
        _emit_progress()

    try:
        _emit_progress(force=True)

        if sort_desc:
            candidates: list[tuple[tuple[int, int, int], dict]] = []
            for shard in _iter_shards(shards_dir):
                for record in _iter_records(shard):
                    if not _matches_record(record):
                        continue
                    candidates.append((_decision_sort_key(record.get("decision_date")), record))
            for _sort_key, record in sorted(candidates, key=lambda item: item[0], reverse=True):
                _ingest_record(record)
                if limit is not None and total_records >= limit:
                    break
            return {
                "records": total_records,
                "chunks": total_chunks,
                "skipped": skipped,
                "skipped_non_criminal": skipped_non_criminal,
                "skipped_seen": skipped_seen,
            }

        if slug_order:
            for slug in slug_order:
                for shard in _iter_shards(shards_dir):
                    for record in _iter_records(shard):
                        if limit is not None and total_records >= limit:
                            return {
                                "records": total_records,
                                "chunks": total_chunks,
                                "skipped": skipped,
                                "skipped_non_criminal": skipped_non_criminal,
                                "skipped_seen": skipped_seen,
                            }
                        reporter = record.get("reporter_slug")
                        if not (isinstance(reporter, str) and reporter.lower() == slug):
                            continue
                        if not _matches_record(record):
                            continue
                        _ingest_record(record)
            return {
                "records": total_records,
                "chunks": total_chunks,
                "skipped": skipped,
                "skipped_non_criminal": skipped_non_criminal,
                "skipped_seen": skipped_seen,
            }

        for shard in _iter_shards(shards_dir):
            for record in _iter_records(shard):
                if not _matches_record(record):
                    continue
                _ingest_record(record)
                if limit is not None and total_records >= limit:
                    return {
                        "records": total_records,
                        "chunks": total_chunks,
                        "skipped": skipped,
                        "skipped_non_criminal": skipped_non_criminal,
                        "skipped_seen": skipped_seen,
                    }

        return {
            "records": total_records,
            "chunks": total_chunks,
            "skipped": skipped,
            "skipped_non_criminal": skipped_non_criminal,
            "skipped_seen": skipped_seen,
        }
    finally:
        _emit_progress(force=True)
        if inspect_handle:
            inspect_handle.close()
        if progress_handle:
            progress_handle.close()


def _refresh_library_indices(base_dir: Path, chroma_dir: Path, summary_mode: str = "heuristic") -> None:
    pdf_map_script = Path("scripts") / "cap_pdf_map.py"
    case_index_script = Path("scripts") / "cap_case_index.py"
    if not pdf_map_script.exists() or not case_index_script.exists():
        return

    summary_mode = summary_mode or "heuristic"
    env = os.environ.copy()
    env["ACQUITTIFY_LIBRARY_SUMMARY_MODE"] = summary_mode

    subprocess.run(
        [
            sys.executable,
            str(pdf_map_script),
            "--base-dir",
            str(base_dir),
            "--output",
            "reports/cap_pdf_index.jsonl",
        ],
        check=False,
        env=env,
    )
    subprocess.run(
        [
            sys.executable,
            str(case_index_script),
            "--chroma-dir",
            str(chroma_dir),
            "--pdf-index",
            "reports/cap_pdf_index.jsonl",
            "--output",
            "reports/cap_case_index.jsonl",
            "--existing-index",
            "reports/cap_case_index.jsonl",
            "--reuse-summaries",
            "--summary-mode",
            summary_mode,
        ],
        check=False,
        env=env,
    )


def _start_summary_worker() -> None:
    worker_script = Path("scripts") / "cap_case_summary_worker.py"
    if not worker_script.exists():
        return
    log_path = Path("reports") / "cap_summary_worker.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log_handle:
        subprocess.Popen(
            [sys.executable, str(worker_script), "--only-missing"],
            stdout=log_handle,
            stderr=log_handle,
        )

def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest CAP JSONL shards into Chroma")
    parser.add_argument("--base-dir", default="acquittify-data", help="Base directory with ingest/cases")
    parser.add_argument("--chroma-dir", default="Corpus/Chroma", help="Chroma directory")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of records to ingest")
    parser.add_argument("--slugs", nargs="*", default=None, help="Reporter slugs to ingest in order")
    parser.add_argument("--min-year", type=int, default=None, help="Minimum decision year (inclusive)")
    parser.add_argument("--max-year", type=int, default=None, help="Maximum decision year (inclusive)")
    parser.add_argument(
        "--court-contains",
        nargs="*",
        default=None,
        help="Case-insensitive substrings to match court name",
    )
    parser.add_argument(
        "--sort-desc",
        action="store_true",
        help="Sort matching records by decision date descending before ingest",
    )
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="Emit JSONL with chunk text + metadata for the first inspected records",
    )
    parser.add_argument("--inspect-records", type=int, default=1, help="Number of records to inspect")
    parser.add_argument("--inspect-chunks", type=int, default=2, help="Chunks per record to inspect")
    parser.add_argument("--inspect-output", default=None, help="Path to write inspection JSONL")
    parser.add_argument(
        "--inspect-no-text",
        action="store_true",
        help="Omit chunk_text from inspection output",
    )
    parser.add_argument(
        "--inspect-all",
        action="store_true",
        help="Log every record (ignores --inspect-records limit)",
    )
    parser.add_argument(
        "--filter-criminal",
        action="store_true",
        help="Skip non-criminal cases (logs reason when inspect is enabled)",
    )
    parser.add_argument(
        "--case-scan-chars",
        type=int,
        default=6000,
        help="Number of characters to scan for criminal/quasi classification",
    )
    parser.add_argument(
        "--case-classify-mode",
        default=None,
        choices=["llm", "heuristic"],
        help="Override case classification mode (llm or heuristic)",
    )
    parser.add_argument(
        "--pause-file",
        default="reports/ingest_CAP_pause.flag",
        help="If this file exists, ingestion pauses until it is removed",
    )
    parser.add_argument(
        "--pause-interval",
        type=float,
        default=5.0,
        help="Seconds between pause checks",
    )
    parser.add_argument(
        "--throttle-seconds",
        type=float,
        default=0.0,
        help="Sleep between records/embeddings to reduce CPU usage",
    )
    parser.add_argument(
        "--resume-log",
        default=None,
        help="Path to inspection log to skip already processed doc_ids",
    )
    parser.add_argument(
        "--progress-log",
        default=None,
        help="Write periodic progress JSONL (e.g., reports/ingest_CAP_progress.jsonl)",
    )
    parser.add_argument(
        "--progress-interval",
        type=int,
        default=500,
        help="Records between progress log entries (0 disables)",
    )
    parser.add_argument(
        "--plan",
        choices=["scotus1975_circuits2010_fedappx2015"],
        default=None,
        help="Run a staged ingest plan",
    )
    parser.add_argument(
        "--no-refresh-library",
        action="store_true",
        help="Disable auto refresh of CAP library indices after ingest",
    )
    args = parser.parse_args()

    shards_dir = Path(args.base_dir) / "ingest" / "cases"
    chroma_dir = Path(args.chroma_dir)

    inspect_output = Path(args.inspect_output) if args.inspect_output else None
    inspect_records = None if args.inspect_all else args.inspect_records
    pause_file = Path(args.pause_file) if args.pause_file else None
    progress_log = Path(args.progress_log) if args.progress_log else None
    if args.plan:
        stages = [
            {
                "name": "scotus_us_1975_plus",
                "slugs": ["us"],
                "court_contains": ["Supreme Court of the United States"],
                "min_year": 1975,
            },
            {
                "name": "federal_circuits_2010_plus",
                "slugs": ["f", "f2d", "f3d", "f4th"],
                "court_contains": ["United States Court of Appeals"],
                "min_year": 2010,
            },
            {
                "name": "federal_appendix_2015_plus",
                "slugs": ["fedappx"],
                "court_contains": ["United States Court of Appeals"],
                "min_year": 2015,
            },
        ]
        summary = {"stages": []}
        for stage in stages:
            stage_summary = ingest_shards(
                shards_dir,
                chroma_dir,
                limit=args.limit,
                slugs=stage["slugs"],
                min_year=stage["min_year"],
                max_year=args.max_year,
                court_contains=stage["court_contains"],
                sort_desc=True,
                inspect=args.inspect,
                inspect_records=inspect_records,
                inspect_chunks=args.inspect_chunks,
                inspect_output=inspect_output,
                inspect_no_text=args.inspect_no_text,
                filter_criminal=args.filter_criminal,
                case_scan_chars=args.case_scan_chars,
                case_classify_mode=args.case_classify_mode,
                pause_file=pause_file,
                pause_check_interval=args.pause_interval,
                throttle_seconds=args.throttle_seconds,
                resume_log=Path(args.resume_log) if args.resume_log else None,
                progress_log=progress_log,
                progress_interval=args.progress_interval,
                stage_name=stage["name"],
            )
            stage_summary["stage"] = stage["name"]
            summary["stages"].append(stage_summary)
        print("ingest_summary", json.dumps(summary))
    else:
        summary = ingest_shards(
            shards_dir,
            chroma_dir,
            limit=args.limit,
            slugs=args.slugs,
            min_year=args.min_year,
            max_year=args.max_year,
            court_contains=args.court_contains,
            sort_desc=args.sort_desc,
            inspect=args.inspect,
            inspect_records=inspect_records,
            inspect_chunks=args.inspect_chunks,
            inspect_output=inspect_output,
            inspect_no_text=args.inspect_no_text,
            filter_criminal=args.filter_criminal,
            case_scan_chars=args.case_scan_chars,
            case_classify_mode=args.case_classify_mode,
            pause_file=pause_file,
            pause_check_interval=args.pause_interval,
            throttle_seconds=args.throttle_seconds,
            resume_log=Path(args.resume_log) if args.resume_log else None,
            progress_log=progress_log,
            progress_interval=args.progress_interval,
        )
        print("ingest_summary", json.dumps(summary))
    if not args.no_refresh_library and os.getenv("ACQUITTIFY_LIBRARY_AUTO_REFRESH", "1") == "1":
        _refresh_library_indices(base_dir=Path(args.base_dir), chroma_dir=chroma_dir)
        if os.getenv("ACQUITTIFY_LIBRARY_BACKGROUND_SUMMARIES", "0") == "1":
            _start_summary_worker()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
