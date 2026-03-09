from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Iterator

import chromadb

from .config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    INDEX_INTERVAL,
    INDEX_PATH,
    MAX_FILE_MB,
    SUPPORTED_EXTENSIONS,
    VAULT_PATH,
)
from .ollama import embed_text
from .text_extract import extract_text_from_eml, extract_text_from_html


EXCLUDE_DIRS = {".obsidian", ".git", "node_modules", "dist", "build"}
MANIFEST_PATH = INDEX_PATH / "manifest.json"


def iter_files(root: Path) -> Iterator[Path]:
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        yield path


def _read_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            import fitz  # PyMuPDF
        except Exception as exc:
            raise RuntimeError("PyMuPDF is required to parse PDF files.") from exc
        text_parts: list[str] = []
        with fitz.open(path) as doc:
            for page in doc:
                text_parts.append(page.get_text())
        return "\n".join(text_parts)

    raw = path.read_text(errors="ignore")
    if suffix == ".html" or suffix == ".htm":
        return extract_text_from_html(raw)
    if suffix == ".eml":
        return extract_text_from_eml(path, raw)
    return raw


def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + chunk_size, length)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == length:
            break
        start = max(0, end - overlap)
    return chunks


def _file_too_large(path: Path) -> bool:
    size_mb = path.stat().st_size / (1024 * 1024)
    return size_mb > MAX_FILE_MB


def _chunk_id(path: Path, chunk_index: int) -> str:
    digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()
    return f"{digest}_{chunk_index}"


def _file_signature(path: Path) -> dict[str, float]:
    stat = path.stat()
    return {"mtime": stat.st_mtime, "size": stat.st_size}


def _load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {"files": {}, "last_indexed": None}
    try:
        return json.loads(MANIFEST_PATH.read_text())
    except Exception:
        return {"files": {}, "last_indexed": None}


def _save_manifest(manifest: dict) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))


def _delete_path_entries(collection, path: Path) -> None:
    path_str = str(path)
    try:
        existing = collection.get(where={"path": path_str}, include=["ids"])
        ids = existing.get("ids", []) if isinstance(existing, dict) else []
        if ids:
            collection.delete(ids=ids)
            return
    except Exception:
        pass
    try:
        collection.delete(where={"path": path_str})
    except Exception:
        return


def _index_file(path: Path, collection) -> bool:
    if _file_too_large(path):
        return False
    try:
        text = _read_text(path)
    except Exception:
        return False

    chunks = _chunk_text(text, CHUNK_SIZE, CHUNK_OVERLAP)
    if not chunks:
        return False

    ids: list[str] = []
    embeddings: list[list[float]] = []
    documents: list[str] = []
    metadatas: list[dict[str, object]] = []

    for idx, chunk in enumerate(chunks):
        chunk_id = _chunk_id(path, idx)
        ids.append(chunk_id)
        embeddings.append(embed_text(chunk))
        documents.append(chunk)
        metadatas.append(
            {
                "path": str(path),
                "chunk_index": idx,
                "total_chunks": len(chunks),
            }
        )

    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
    )
    return True


def manifest_stats() -> dict:
    manifest = _load_manifest()
    files = manifest.get("files", {}) if isinstance(manifest, dict) else {}
    return {
        "tracked_files": len(files),
        "last_indexed": manifest.get("last_indexed"),
    }


def build_index(limit: int | None = None, rebuild: bool = False) -> dict:
    INDEX_PATH.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(INDEX_PATH))

    if rebuild:
        try:
            client.delete_collection("peregrine_vault")
        except Exception:
            pass
        manifest = {"files": {}, "last_indexed": None}
    else:
        manifest = _load_manifest()

    collection = client.get_or_create_collection("peregrine_vault")

    files = list(iter_files(VAULT_PATH))
    if limit:
        files = files[:limit]

    manifest_files = manifest.get("files", {}) if isinstance(manifest, dict) else {}
    seen_paths: set[str] = set()

    added = 0
    updated = 0
    skipped = 0
    removed = 0
    errors = 0

    for path in files:
        path_str = str(path)
        seen_paths.add(path_str)

        signature = _file_signature(path)
        prior = manifest_files.get(path_str)

        if prior == signature:
            skipped += 1
            continue

        try:
            _delete_path_entries(collection, path)
            if _index_file(path, collection):
                if prior is None:
                    added += 1
                else:
                    updated += 1
                manifest_files[path_str] = signature
            else:
                errors += 1
        except Exception:
            errors += 1

    if limit is None:
        for path_str in list(manifest_files.keys()):
            if path_str not in seen_paths:
                try:
                    _delete_path_entries(collection, Path(path_str))
                except Exception:
                    pass
                manifest_files.pop(path_str, None)
                removed += 1

    manifest["files"] = manifest_files
    manifest["last_indexed"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _save_manifest(manifest)

    return {
        "indexed_files": added,
        "updated_files": updated,
        "removed_files": removed,
        "skipped_files": skipped,
        "errors": errors,
        "total_files": len(files),
    }


def watch_index(interval: int | None = None) -> None:
    poll = interval or INDEX_INTERVAL
    while True:
        build_index()
        time.sleep(poll)
