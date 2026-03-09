#!/usr/bin/env python3
"""Download CAP federal reporter corpora from static.case.law with resume + verification."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import deque
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, List, Optional
from urllib.parse import urljoin, urlparse

import requests

BASE_URL = "https://static.case.law/"
SLUGS = [
    "alaska-fed",
    "ccpa",
    "cma",
    "ct-cust",
    "ct-intl-trade",
    "cust-ct",
    "d-haw",
    "ed-pa",
    "f",
    "f-appx",
    "f-cas",
    "f-supp",
    "f-supp-2d",
    "f-supp-3d",
    "f2d",
    "f3d",
    "fed-cl",
    "frd",
    "n-mar-i-commw",
    "pr-fed",
    "us",
    "us-app-dc",
    "us-ct-cl",
    "vet-app",
]

ROOT_METADATA = [
    "ReportersMetadata.json",
    "VolumesMetadata.json",
    "JurisdictionsMetadata.json",
]


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: List[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.hrefs.append(value)


@dataclass
class DownloadResult:
    url: str
    local_path: str
    status: str
    bytes: int
    sha256: str
    error: str | None = None


class RateLimiter:
    def __init__(self, min_interval: float) -> None:
        self.min_interval = min_interval
        self.last_time: float | None = None

    def wait(self) -> None:
        now = time.time()
        if self.last_time is None:
            self.last_time = now
            return
        elapsed = now - self.last_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_time = time.time()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _request_with_backoff(session: requests.Session, method: str, url: str, **kwargs):
    retries = 5
    backoff = 1.0
    for attempt in range(1, retries + 1):
        try:
            return session.request(method, url, timeout=30, **kwargs)
        except requests.RequestException:
            if attempt == retries:
                raise
            time.sleep(backoff)
            backoff *= 2


def _fetch_html(session: requests.Session, limiter: RateLimiter, url: str) -> str:
    limiter.wait()
    response = _request_with_backoff(session, "GET", url)
    response.raise_for_status()
    return response.text


def _crawl_slug(session: requests.Session, limiter: RateLimiter, slug: str) -> list[str]:
    base = urljoin(BASE_URL, f"{slug}/")
    seen = set()
    files: set[str] = set()
    queue = deque([base])
    while queue:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        html = _fetch_html(session, limiter, current)
        parser = LinkParser()
        parser.feed(html)
        for href in parser.hrefs:
            if href.startswith("../") or href.startswith("./"):
                href = href.replace("./", "")
            target = urljoin(current, href)
            if not target.startswith(base):
                continue
            parsed = urlparse(target)
            clean = parsed._replace(fragment="", query="").geturl()
            if clean.endswith("/"):
                if clean not in seen:
                    queue.append(clean)
            else:
                files.add(clean)
    return sorted(files)


def _download_file(
    session: requests.Session,
    limiter: RateLimiter,
    url: str,
    dest: Path,
) -> DownloadResult:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return DownloadResult(url, str(dest), "skipped", dest.stat().st_size, _sha256_path(dest))

    tmp_path = dest.with_suffix(dest.suffix + ".part")
    limiter.wait()
    response = _request_with_backoff(session, "GET", url, stream=True)
    response.raise_for_status()
    digest = hashlib.sha256()
    total = 0
    with tmp_path.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if not chunk:
                continue
            handle.write(chunk)
            digest.update(chunk)
            total += len(chunk)
    tmp_path.replace(dest)
    return DownloadResult(url, str(dest), "downloaded", total, digest.hexdigest())


def _write_manifest(path: Path, results: Iterable[DownloadResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result.__dict__, ensure_ascii=False) + "\n")


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _write_checkpoint(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _append_download_log(path: Path, payload: dict) -> None:
    _append_jsonl(path, payload)


def _report_missing(slug: str, expected: list[str], raw_root: Path, logs_dir: Path) -> int:
    missing = []
    for url in expected:
        rel = urlparse(url).path.lstrip("/")
        local = raw_root / rel
        if not local.exists() or local.stat().st_size == 0:
            missing.append(url)
    if not missing:
        return 0
    report_path = logs_dir / f"missing_{slug}.txt"
    report_path.write_text("\n".join(missing) + "\n", encoding="utf-8")
    return len(missing)


def main() -> int:
    parser = argparse.ArgumentParser(description="Download CAP federal reporters from static.case.law")
    parser.add_argument("--base-dir", default="acquittify-data", help="Output base directory")
    parser.add_argument("--slugs", nargs="*", default=SLUGS, help="Reporter slugs to download")
    parser.add_argument("--rate", type=float, default=1.0, help="Minimum seconds between requests")
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=50,
        help="Write a checkpoint every N files (per slug)",
    )
    args = parser.parse_args()

    base_dir = Path(args.base_dir)
    raw_root = base_dir / "raw" / "static.case.law"
    logs_dir = base_dir / "logs"
    raw_root.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    limiter = RateLimiter(args.rate)

    manifest_path = logs_dir / "download_manifest.jsonl"
    progress_path = logs_dir / "download_progress.jsonl"
    checkpoint_path = logs_dir / "download_checkpoint.json"
    checkpoints_path = logs_dir / "download_checkpoints.jsonl"
    log_path = logs_dir / "download_federal.log"

    _append_download_log(
        log_path,
        {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "event": "start",
            "slugs": args.slugs,
            "rate": args.rate,
            "checkpoint_every": args.checkpoint_every,
        },
    )

    # Download root metadata
    metadata_results: list[DownloadResult] = []
    for name in ROOT_METADATA:
        url = urljoin(BASE_URL, name)
        dest = raw_root / name
        result = _download_file(session, limiter, url, dest)
        metadata_results.append(result)
        _append_jsonl(
            progress_path,
            {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "slug": "__metadata__",
                "index": len(metadata_results),
                "total": len(ROOT_METADATA),
                "status": result.status,
                "bytes": result.bytes,
                "url": result.url,
                "local_path": result.local_path,
                "sha256": result.sha256,
                "error": result.error,
            },
        )
    _write_manifest(manifest_path, metadata_results)

    missing_total = 0
    for slug in args.slugs:
        if slug not in SLUGS:
            print(f"Skipping non-federal slug: {slug}", file=sys.stderr)
            continue
        print(f"Crawling {slug}...")
        urls = _crawl_slug(session, limiter, slug)
        if not urls:
            print(f"No files discovered for {slug}", file=sys.stderr)
        results: list[DownloadResult] = []
        downloaded = 0
        skipped = 0
        failed = 0
        bytes_total = 0
        total = len(urls)
        for idx, url in enumerate(urls, start=1):
            rel = urlparse(url).path.lstrip("/")
            dest = raw_root / rel
            try:
                result = _download_file(session, limiter, url, dest)
            except requests.RequestException as exc:
                result = DownloadResult(url, str(dest), "failed", 0, "", str(exc))
            results.append(result)
            if result.status == "downloaded":
                downloaded += 1
            elif result.status == "skipped":
                skipped += 1
            else:
                failed += 1
            bytes_total += result.bytes
            _append_jsonl(
                progress_path,
                {
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "slug": slug,
                    "index": idx,
                    "total": total,
                    "status": result.status,
                    "bytes": result.bytes,
                    "downloaded": downloaded,
                    "skipped": skipped,
                    "failed": failed,
                    "bytes_total": bytes_total,
                    "url": result.url,
                    "local_path": result.local_path,
                    "sha256": result.sha256,
                    "error": result.error,
                },
            )
            if args.checkpoint_every > 0 and idx % args.checkpoint_every == 0:
                checkpoint = {
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "slug": slug,
                    "index": idx,
                    "total": total,
                    "downloaded": downloaded,
                    "skipped": skipped,
                    "failed": failed,
                    "bytes_total": bytes_total,
                    "last_url": result.url,
                    "last_path": result.local_path,
                }
                _write_checkpoint(checkpoint_path, checkpoint)
                _append_jsonl(checkpoints_path, checkpoint)
                _append_download_log(
                    log_path,
                    {
                        "ts": checkpoint["ts"],
                        "event": "checkpoint",
                        **checkpoint,
                    },
                )
        _write_manifest(manifest_path, results)
        if total > 0:
            checkpoint = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "slug": slug,
                "index": total,
                "total": total,
                "downloaded": downloaded,
                "skipped": skipped,
                "failed": failed,
                "bytes_total": bytes_total,
                "last_url": urls[-1] if urls else None,
                "last_path": str(raw_root / urlparse(urls[-1]).path.lstrip("/")) if urls else None,
                "slug_complete": True,
            }
            _write_checkpoint(checkpoint_path, checkpoint)
            _append_jsonl(checkpoints_path, checkpoint)
            _append_download_log(
                log_path,
                {
                    "ts": checkpoint["ts"],
                    "event": "slug_complete",
                    **checkpoint,
                },
            )
        missing_total += _report_missing(slug, urls, raw_root, logs_dir)

    if missing_total > 0:
        _append_download_log(
            log_path,
            {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "event": "complete",
                "missing_total": missing_total,
                "status": "missing_files",
            },
        )
        print(f"Missing files detected: {missing_total}", file=sys.stderr)
        return 2

    _append_download_log(
        log_path,
        {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "event": "complete",
            "missing_total": 0,
            "status": "ok",
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
