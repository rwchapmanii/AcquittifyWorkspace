#!/usr/bin/env python3
"""Normalize CAP static.case.law dumps into Acquittify ingest JSONL shards."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Tuple
from urllib.parse import urlparse

BASE_DIR_DEFAULT = "acquittify-data"
RAW_SUBDIR = Path("raw") / "static.case.law"


@dataclass
class ShardState:
    shard_index: int
    shard_path: Path
    records_in_shard: int
    bytes_in_shard: int
    handle: object


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_commit() -> str | None:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except Exception:
        return None


def _load_manifest_map(logs_dir: Path) -> Dict[str, str]:
    manifest = logs_dir / "download_manifest.jsonl"
    mapping: Dict[str, str] = {}
    if not manifest.exists():
        return mapping
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        url = payload.get("url")
        local_path = payload.get("local_path")
        if isinstance(url, str) and isinstance(local_path, str):
            mapping[local_path] = url
    return mapping


def _iter_raw_files(raw_root: Path) -> Iterator[Path]:
    for path in sorted(raw_root.rglob("*.json")):
        if "cases" in path.parts:
            yield path
    for path in sorted(raw_root.rglob("*.jsonl")):
        if "cases" in path.parts:
            yield path


def _extract_text(record: dict) -> Tuple[str, str]:
    casebody = record.get("casebody")
    if isinstance(casebody, dict):
        data = casebody.get("data") or ""
        fmt = casebody.get("format") or "unknown"
        if data:
            return data, str(fmt)

        opinions = casebody.get("opinions")
        if isinstance(opinions, list):
            best_text = ""
            best_type = "unknown"
            for opinion in opinions:
                if not isinstance(opinion, dict):
                    continue
                for field, kind in (("text", "plain"), ("html", "html"), ("xml", "xml")):
                    value = opinion.get(field)
                    if value and len(str(value)) > len(best_text):
                        best_text = str(value)
                        best_type = kind
            if best_text:
                return best_text, best_type

    opinions = record.get("opinions")
    if isinstance(opinions, list):
        best_text = ""
        best_type = "unknown"
        for opinion in opinions:
            if not isinstance(opinion, dict):
                continue
            for field, kind in (("text", "plain"), ("html", "html"), ("xml", "xml")):
                value = opinion.get(field)
                if value and len(str(value)) > len(best_text):
                    best_text = str(value)
                    best_type = kind
        if best_text:
            return best_text, best_type

    for field, kind in (("opinion_text", "plain"), ("text", "plain"), ("html", "html"), ("xml", "xml")):
        value = record.get(field)
        if value:
            return str(value), kind

    return "", "unknown"


def _extract_citations(record: dict) -> List:
    citations = record.get("citations")
    if isinstance(citations, list):
        return citations
    cite = record.get("citation")
    if cite:
        return [cite]
    return []


def _normalize_record(
    record: dict,
    reporter_slug: str,
    raw_file: Path,
    raw_sha: str,
    download_url: str | None,
) -> dict:
    text, text_type = _extract_text(record)
    output = {
        "source": "cap-static-case-law",
        "reporter_slug": reporter_slug,
        "jurisdiction": record.get("jurisdiction") or record.get("jurisdiction_id"),
        "court": record.get("court") or record.get("court_id"),
        "decision_date": record.get("decision_date") or record.get("date"),
        "docket_number": record.get("docket_number"),
        "case_name": record.get("name") or record.get("case_name") or record.get("title"),
        "citations": _extract_citations(record),
        "volume": record.get("volume") or record.get("volume_number"),
        "page": record.get("page") or record.get("first_page"),
        "opinion_text": text,
        "opinion_text_type": text_type,
        "cap_id": record.get("id") or record.get("case_id"),
        "download_url": download_url or f"file://{raw_file}",
        "sha256_raw_file": raw_sha,
    }
    if not text:
        output["error"] = "missing_opinion_text"
    return output


def _iter_records(payload: object) -> Iterator[dict]:
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield item
        return
    if isinstance(payload, dict):
        for key in ("cases", "results", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        yield item
                return
        yield payload


def _open_new_shard(out_dir: Path, index: int) -> ShardState:
    out_dir.mkdir(parents=True, exist_ok=True)
    shard_path = out_dir / f"cases_{index:06d}.jsonl"
    handle = shard_path.open("w", encoding="utf-8")
    return ShardState(index, shard_path, 0, 0, handle)


def _close_shard(state: ShardState) -> None:
    if state.handle:
        state.handle.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize CAP dumps into Acquittify JSONL shards")
    parser.add_argument("--base-dir", default=BASE_DIR_DEFAULT, help="Base output directory")
    parser.add_argument("--shard-bytes", type=int, default=250 * 1024 * 1024, help="Target shard size in bytes")
    parser.add_argument("--shard-records", type=int, default=200000, help="Max records per shard")
    args = parser.parse_args()

    base_dir = Path(args.base_dir)
    raw_root = base_dir / RAW_SUBDIR
    ingest_dir = base_dir / "ingest" / "cases"
    manifest_dir = base_dir / "ingest" / "manifest"
    logs_dir = base_dir / "logs"

    if not raw_root.exists():
        raise SystemExit(f"Missing raw directory: {raw_root}")

    download_map = _load_manifest_map(logs_dir)

    shard = _open_new_shard(ingest_dir, 1)
    total_records = 0
    raw_files_count = 0
    raw_bytes = 0
    records_by_reporter: Dict[str, int] = {}
    records_by_reporter_volume: Dict[str, Dict[str, int]] = {}

    ingest_files: List[dict] = []

    for raw_file in _iter_raw_files(raw_root):
        raw_files_count += 1
        raw_bytes += raw_file.stat().st_size
        raw_sha = _sha256_path(raw_file)
        reporter_slug = raw_file.relative_to(raw_root).parts[0]
        download_url = download_map.get(str(raw_file))

        def _records_from_file(path: Path) -> Iterator[dict]:
            if path.suffix == ".jsonl":
                with path.open("r", encoding="utf-8", errors="replace") as handle:
                    for line in handle:
                        if not line.strip():
                            continue
                        try:
                            payload = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        yield from _iter_records(payload)
                return
            try:
                payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            except json.JSONDecodeError:
                return
            yield from _iter_records(payload)

        for record in _records_from_file(raw_file):
            normalized = _normalize_record(record, reporter_slug, raw_file, raw_sha, download_url)
            line = json.dumps(normalized, ensure_ascii=False)
            encoded = (line + "\n").encode("utf-8")
            shard.handle.write(line + "\n")
            shard.records_in_shard += 1
            shard.bytes_in_shard += len(encoded)
            total_records += 1

            records_by_reporter[reporter_slug] = records_by_reporter.get(reporter_slug, 0) + 1
            volume = str(normalized.get("volume") or "unknown")
            records_by_reporter_volume.setdefault(reporter_slug, {})
            records_by_reporter_volume[reporter_slug][volume] = (
                records_by_reporter_volume[reporter_slug].get(volume, 0) + 1
            )

            if shard.bytes_in_shard >= args.shard_bytes or shard.records_in_shard >= args.shard_records:
                _close_shard(shard)
                ingest_files.append({
                    "path": str(shard.shard_path),
                    "bytes": shard.shard_path.stat().st_size,
                    "sha256": _sha256_path(shard.shard_path),
                    "record_count": shard.records_in_shard,
                })
                shard = _open_new_shard(ingest_dir, shard.shard_index + 1)

    _close_shard(shard)
    if shard.shard_path.exists() and shard.records_in_shard:
        ingest_files.append({
            "path": str(shard.shard_path),
            "bytes": shard.shard_path.stat().st_size,
            "sha256": _sha256_path(shard.shard_path),
            "record_count": shard.records_in_shard,
        })
    elif shard.shard_path.exists():
        shard.shard_path.unlink()

    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "total_records": total_records,
        "records_by_reporter_slug": records_by_reporter,
        "records_by_reporter_volume": records_by_reporter_volume,
        "raw_files_count": raw_files_count,
        "raw_bytes": raw_bytes,
        "ingest_files": ingest_files,
        "run_timestamp": datetime.utcnow().isoformat() + "Z",
        "git_commit": _git_commit(),
    }

    manifest_path = manifest_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))

    checksums_path = manifest_dir / "checksums.txt"
    with checksums_path.open("w", encoding="utf-8") as handle:
        for item in ingest_files:
            handle.write(f"{item['sha256']}  {item['path']}\n")

    print("Final summary:")
    for slug in sorted(records_by_reporter.keys()):
        print(f"  {slug}: {records_by_reporter[slug]}")
    print(f"Total records: {total_records}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
