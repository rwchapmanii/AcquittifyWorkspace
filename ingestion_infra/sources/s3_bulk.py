"""Bulk CSV ingestion from S3."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Iterator, List, Tuple
import logging
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
import xml.etree.ElementTree as ET

import boto3
from botocore import UNSIGNED
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError
import requests

from ingestion_infra.config import Settings
from ingestion_infra.utils.csv_stream import iter_csv_rows_from_s3

LOGGER = logging.getLogger(__name__)

ENTITY_ID_COLUMNS = {
    "courts": "id",
    "dockets": "id",
    "opinion-clusters": "id",
    "opinions": "id",
    "opinion-texts": "id",
}

ENTITY_KEY_PATTERNS = {
    "courts": re.compile(r"/courts-[^/]+\.csv(\.(gz|bz2|xz))?$", re.IGNORECASE),
    "dockets": re.compile(r"/dockets-[^/]+\.csv(\.(gz|bz2|xz))?$", re.IGNORECASE),
    "opinion-clusters": re.compile(r"/opinion[-_]clusters-[^/]+\.csv(\.(gz|bz2|xz))?$", re.IGNORECASE),
    "opinions": re.compile(r"/opinions-[^/]+\.csv(\.(gz|bz2|xz))?$", re.IGNORECASE),
    "opinion-texts": re.compile(r"/opinion[-_]texts-[^/]+\.csv(\.(gz|bz2|xz))?$", re.IGNORECASE),
}


@dataclass
class S3ObjectRef:
    bucket: str
    key: str


class S3BulkSource:
    """Bulk CSV source for CourtListener snapshots."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        config = None
        if settings.s3_unsigned:
            config = BotoConfig(
                signature_version=UNSIGNED,
                read_timeout=900,
                connect_timeout=60,
                retries={"max_attempts": 20, "mode": "adaptive"},
                tcp_keepalive=True,
                s3={"addressing_style": settings.s3_addressing_style},
            )
        self.client = boto3.client(
            "s3",
            region_name=settings.s3_region,
            endpoint_url=settings.s3_endpoint_url,
            config=config,
        )

    def resolve_keys(self, entity: str) -> List[str]:
        """Resolve S3 keys for an entity either from config or prefix listing."""
        configured = self.settings.bulk_keys().get(entity)
        if configured:
            return configured

        prefix = f"{self.settings.s3_prefix}/"
        keys: List[str] = []
        pattern = ENTITY_KEY_PATTERNS.get(entity)
        paginator = self.client.get_paginator("list_objects_v2")
        try:
            for page in paginator.paginate(Bucket=self.settings.s3_bucket, Prefix=prefix):
                for item in page.get("Contents", []):
                    key = item["Key"]
                    if pattern and pattern.search(key):
                        keys.append(key)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code == "AccessDenied":
                LOGGER.warning(
                    "S3 listing is forbidden for %s; attempting bulk-data index fallback. "
                    "Set COURTLISTENER_BULK_KEYS_JSON to provide explicit keys.",
                    prefix,
                )
                keys = self._resolve_keys_from_bulk_data_index(entity)
            else:
                raise

        if not keys:
            fallback = self._resolve_keys_from_bulk_data_index(entity)
            if fallback:
                keys = fallback

        if not keys:
            LOGGER.warning("No keys found for %s under %s", entity, prefix)
        return sorted(set(keys))

    def _resolve_keys_from_bulk_data_index(self, entity: str) -> List[str]:
        pattern = ENTITY_KEY_PATTERNS.get(entity)
        if not pattern:
            return []

        def extract_key(value: str) -> str | None:
            if not value:
                return None
            if value.startswith("s3://"):
                parsed = urlparse(value)
                return parsed.path.lstrip("/")
            if value.startswith("http://") or value.startswith("https://"):
                parsed = urlparse(value)
                if parsed.netloc.endswith("s3.amazonaws.com"):
                    return parsed.path.lstrip("/")
                if parsed.netloc.endswith("amazonaws.com"):
                    return parsed.path.lstrip("/")
                if parsed.path.startswith("/bulk-data/"):
                    return parsed.path.lstrip("/")
                return None
            return value

        def update_marker(current_url: str, marker_value: str) -> str:
            parsed = urlparse(current_url)
            params = parse_qs(parsed.query)
            params["marker"] = [marker_value]
            new_query = urlencode(params, doseq=True)
            return urlunparse(
                (
                    parsed.scheme,
                    parsed.netloc,
                    parsed.path,
                    parsed.params,
                    new_query,
                    parsed.fragment,
                )
            )

        headers = {}
        if self.settings.api_token:
            headers["Authorization"] = f"Token {self.settings.api_token}"

        url = self.settings.bulk_data_url
        keys: List[str] = []
        visited = 0
        while url and visited < 20:
            visited += 1
            try:
                resp = requests.get(url, headers=headers, timeout=30)
            except Exception:
                break
            if resp.status_code != 200:
                LOGGER.warning("Bulk-data index request failed (%s): %s", resp.status_code, url)
                break
            content_type = resp.headers.get("Content-Type", "")
            is_json = "json" in content_type.lower()
            payload = None
            if is_json:
                try:
                    payload = resp.json()
                except Exception:
                    payload = None

            if payload is None:
                xml_root = None
                if "xml" in content_type.lower() or "ListBucketResult" in resp.text:
                    try:
                        xml_root = ET.fromstring(resp.text)
                    except Exception:
                        xml_root = None

                if xml_root is not None:
                    page_keys: List[str] = []
                    for key_node in xml_root.findall(".//{*}Contents/{*}Key"):
                        key = key_node.text or ""
                        if key and pattern.search(key):
                            keys.append(key)
                            page_keys.append(key)
                    truncated = (xml_root.findtext(".//{*}IsTruncated") or "").lower() == "true"
                    if truncated:
                        next_marker = xml_root.findtext(".//{*}NextMarker") or (page_keys[-1] if page_keys else None)
                        if next_marker:
                            url = update_marker(url, next_marker)
                            continue
                    url = None
                    continue

                hrefs = re.findall(r"href=[\"']([^\"']+)[\"']", resp.text)
                for href in hrefs:
                    key = extract_key(href)
                    if key and "/" not in key and self.settings.s3_prefix:
                        key = f"{self.settings.s3_prefix}/{key}"
                    if key and pattern.search(key):
                        keys.append(key)
                url = None
                continue

            results = payload
            if isinstance(payload, dict):
                results = payload.get("results") or payload.get("data") or payload.get("objects") or payload.get("files") or []

            if isinstance(results, list):
                for item in results:
                    if not isinstance(item, dict):
                        continue
                    for field in (
                        "s3_key",
                        "key",
                        "path",
                        "filename",
                        "file_name",
                        "download_url",
                        "url",
                        "s3_url",
                    ):
                        raw = item.get(field)
                        if not isinstance(raw, str):
                            continue
                        key = extract_key(raw)
                        if key and pattern.search(key):
                            keys.append(key)

            if isinstance(payload, dict):
                url = payload.get("next") or payload.get("next_url")
            else:
                url = None

        if keys:
            LOGGER.info("Resolved %d keys for %s from bulk-data index.", len(keys), entity)
        return keys

    def iter_csv_rows(self, entity: str, key: str, start_row: int = 1) -> Iterator[Tuple[int, Dict]]:
        """Stream CSV rows from S3 without loading full file."""
        return iter_csv_rows_from_s3(
            self.client,
            self.settings.s3_bucket,
            key,
            start_row=start_row,
            http_fallback_url=self.settings.s3_http_fallback_url,
        )

    def get_record_id(self, entity: str, row: Dict) -> str | None:
        """Extract stable id from bulk CSV row."""
        column = ENTITY_ID_COLUMNS.get(entity)
        if not column:
            return None
        value = row.get(column)
        return str(value) if value is not None else None
