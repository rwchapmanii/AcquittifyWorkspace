#!/usr/bin/env python3
"""Sanity-check S3 endpoint connectivity with a small ranged read."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingestion_infra.config import Settings
from ingestion_infra.sources.s3_bulk import S3BulkSource


def main() -> None:
    parser = argparse.ArgumentParser(description="Check S3 endpoint connectivity.")
    parser.add_argument("--key", required=True, help="S3 key to read (e.g., bulk-data/opinions-2022-08-02.csv.bz2)")
    parser.add_argument("--bytes", type=int, default=1024, help="Number of bytes to read")
    args = parser.parse_args()

    settings = Settings()
    source = S3BulkSource(settings)

    source_used = "s3"
    try:
        response = source.client.get_object(
            Bucket=settings.s3_bucket,
            Key=args.key,
            Range=f"bytes=0-{args.bytes - 1}",
        )
        chunk = response["Body"].read(args.bytes)
    except Exception:
        if not settings.s3_http_fallback_url:
            raise
        source_used = "http"
        url = f"{settings.s3_http_fallback_url.rstrip('/')}/{args.key.lstrip('/')}"
        resp = requests.get(url, stream=True, timeout=60)
        resp.raise_for_status()
        resp.raw.decode_content = True
        chunk = resp.raw.read(args.bytes)

    print("source=", source_used)
    print("read_bytes=", len(chunk))


if __name__ == "__main__":
    main()
