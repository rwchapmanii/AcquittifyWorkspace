"""Streaming CSV utilities for S3 objects."""

from __future__ import annotations

import bz2
import csv
import gzip
import lzma
from io import TextIOWrapper
import sys
from typing import Dict, Iterator, Tuple

from botocore.exceptions import EndpointConnectionError
import requests


def iter_csv_rows_from_s3(
    s3_client,
    bucket: str,
    key: str,
    start_row: int = 1,
    http_fallback_url: str | None = None,
) -> Iterator[Tuple[int, Dict]]:
    """Yield row number and row dict from an S3 CSV (optionally compressed)."""
    body = None
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        body = response["Body"]
    except EndpointConnectionError:
        if not http_fallback_url:
            raise
        url = f"{http_fallback_url.rstrip('/')}/{key.lstrip('/')}"
        resp = requests.get(url, stream=True, timeout=60)
        resp.raise_for_status()
        resp.raw.decode_content = True
        body = resp.raw

    if key.endswith(".gz"):
        stream = gzip.GzipFile(fileobj=body)
        text_stream = TextIOWrapper(stream, encoding="utf-8")
    elif key.endswith(".bz2"):
        stream = bz2.BZ2File(body)
        text_stream = TextIOWrapper(stream, encoding="utf-8")
    elif key.endswith(".xz"):
        stream = lzma.LZMAFile(body)
        text_stream = TextIOWrapper(stream, encoding="utf-8")
    else:
        text_stream = TextIOWrapper(body, encoding="utf-8")

    reader = csv.DictReader(text_stream)
    try:
        csv.field_size_limit(sys.maxsize)
    except OverflowError:
        csv.field_size_limit(2**31 - 1)
    for index, row in enumerate(reader, start=1):
        if index < start_row:
            continue
        yield index, row
