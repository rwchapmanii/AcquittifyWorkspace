#!/usr/bin/env python3
"""Build a cached index mapping CAP metadata records to local PDF paths."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Iterable, Iterator, Optional, Set
from urllib.parse import urlparse

import chromadb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from acquittify.config import CHROMA_COLLECTION


DEFAULT_BASE_DIR = Path("acquittify-data")
DEFAULT_MANIFEST = DEFAULT_BASE_DIR / "logs" / "download_manifest.jsonl"
DEFAULT_OUTPUT = Path("reports") / "cap_pdf_index.jsonl"


def _load_manifest_map(manifest_path: Path) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    if not manifest_path.exists():
        return mapping
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        url = payload.get("url")
        local_path = payload.get("local_path")
        if isinstance(url, str) and isinstance(local_path, str):
            mapping[url] = local_path
    return mapping


def _iter_jsonl(path: Path) -> Iterator[dict]:
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


def _maybe_extract_metadata(payload: dict) -> dict:
    # CAP inspect JSONL stores metadata under "metadata"
    meta = payload.get("metadata")
    if isinstance(meta, dict):
        return meta
    return payload


def _local_path_from_url(base_dir: Path, url: str) -> Optional[Path]:
    if url.startswith("file://"):
        return Path(url.replace("file://", "", 1))
    if url.startswith("http://") or url.startswith("https://"):
        parsed = urlparse(url)
        suffix = parsed.path.lstrip("/")
        return base_dir / "raw" / "static.case.law" / suffix
    # treat as relative path if it contains static.case.law
    if "static.case.law" in url:
        parts = url.split("static.case.law", 1)[-1].lstrip("/")
        return base_dir / "raw" / "static.case.law" / parts
    return None


def _pdf_path_from_case_json(case_json_path: Path) -> Path:
    path_str = str(case_json_path)
    if "/cases/" in path_str:
        path_str = path_str.replace("/cases/", "/case-pdfs/")
    if path_str.endswith(".json"):
        path_str = path_str[:-5] + ".pdf"
    return Path(path_str)


def _pdf_url_from_case_url(case_url: str) -> Optional[str]:
    if not (case_url.startswith("http://") or case_url.startswith("https://")):
        return None
    if "/cases/" in case_url:
        case_url = case_url.replace("/cases/", "/case-pdfs/")
    if case_url.endswith(".json"):
        case_url = case_url[:-5] + ".pdf"
    return case_url


def _resolve_pdf_path(
    meta: dict,
    base_dir: Path,
    manifest_map: Dict[str, str],
) -> tuple[Optional[str], str]:
    source_url = meta.get("download_url") or meta.get("path")
    if isinstance(source_url, str):
        local_case_path = _local_path_from_url(base_dir, source_url)
        if local_case_path:
            candidate = _pdf_path_from_case_json(local_case_path)
            if candidate.exists():
                return str(candidate), "local_transform"

        pdf_url = _pdf_url_from_case_url(source_url)
        if pdf_url and pdf_url in manifest_map:
            local_path = Path(manifest_map[pdf_url])
            if local_path.exists():
                return str(local_path), "manifest_url"

    return None, "missing"


def _iter_chroma_metadata(
    chroma_dir: Path, collection_name: str, limit: Optional[int] = None
) -> Iterator[dict]:
    client = chromadb.PersistentClient(path=str(chroma_dir))
    collection = client.get_collection(name=collection_name)
    total = collection.count()
    if limit is not None:
        total = min(total, limit)

    offset = 0
    batch = 5000
    while offset < total:
        fetch = min(batch, total - offset)
        res = collection.get(limit=fetch, offset=offset, include=["metadatas"])
        metas = res.get("metadatas") or []
        for meta in metas:
            if isinstance(meta, dict):
                yield meta
        offset += fetch


def build_index(
    *,
    base_dir: Path,
    manifest_path: Path,
    output_path: Path,
    chroma_dir: Optional[Path],
    collection: str,
    metadata_jsonl: Optional[Path],
    limit: Optional[int],
) -> dict:
    manifest_map = _load_manifest_map(manifest_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    seen: Set[str] = set()
    total = 0
    matched = 0
    missing = 0

    if metadata_jsonl:
        source_iter = (_maybe_extract_metadata(payload) for payload in _iter_jsonl(metadata_jsonl))
    else:
        if chroma_dir is None:
            raise SystemExit("Provide --chroma-dir or --metadata-jsonl")
        source_iter = _iter_chroma_metadata(chroma_dir, collection, limit=limit)

    with output_path.open("w", encoding="utf-8") as handle:
        for meta in source_iter:
            doc_id = meta.get("doc_id")
            source = meta.get("source")
            if not isinstance(doc_id, str) or not doc_id.startswith("cap_"):
                if source != "cap-static-case-law":
                    continue
            if doc_id in seen:
                continue
            seen.add(doc_id)
            total += 1

            pdf_path, method = _resolve_pdf_path(meta, base_dir, manifest_map)
            if pdf_path:
                matched += 1
            else:
                missing += 1

            record = {
                "doc_id": doc_id,
                "cap_id": meta.get("cap_id"),
                "case_name": meta.get("case_name") or meta.get("title"),
                "court": meta.get("court"),
                "decision_date": meta.get("decision_date") or meta.get("date"),
                "citations": meta.get("citations"),
                "document_citation": meta.get("document_citation"),
                "reporter_slug": meta.get("reporter_slug"),
                "download_url": meta.get("download_url"),
                "path": meta.get("path"),
                "pdf_path": pdf_path,
                "mapping_method": method,
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    return {
        "total_docs": total,
        "pdf_mapped": matched,
        "missing_pdf": missing,
        "output": str(output_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a cached CAP PDF mapping index.")
    parser.add_argument("--base-dir", default=str(DEFAULT_BASE_DIR), help="Base data directory")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="Download manifest JSONL")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output JSONL index")
    parser.add_argument("--chroma-dir", default=str(Path("Corpus") / "Chroma"), help="Chroma directory")
    parser.add_argument("--collection", default=CHROMA_COLLECTION, help="Chroma collection name")
    parser.add_argument(
        "--metadata-jsonl",
        default=None,
        help="Optional JSONL with CAP metadata (bypasses Chroma scan)",
    )
    parser.add_argument("--limit", type=int, default=None, help="Limit documents scanned")
    args = parser.parse_args()

    summary = build_index(
        base_dir=Path(args.base_dir),
        manifest_path=Path(args.manifest),
        output_path=Path(args.output),
        chroma_dir=Path(args.chroma_dir) if args.metadata_jsonl is None else None,
        collection=args.collection,
        metadata_jsonl=Path(args.metadata_jsonl) if args.metadata_jsonl else None,
        limit=args.limit,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
