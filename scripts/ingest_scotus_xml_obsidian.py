#!/usr/bin/env python3
"""Ingest Supreme Court XML corpus into an Obsidian vault with PDF+Markdown pairs.

This script:
1) Creates/updates an Obsidian vault directory.
2) Pulls XML files from Supreme Court XML archive/current endpoints.
3) Resolves matching official PDF URLs from Supreme Court opinion/order index pages.
4) Stores per-case XML + native PDF + Markdown extracted text.
5) Builds a lightweight ontology DB so Acquittify can link case -> native file.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import html
import json
import os
import re
import sqlite3
import subprocess
import threading
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from acquittify.paths import OBSIDIAN_ROOT

SCOTUS_ROOT = "https://www.supremecourt.gov"
XML_ARCHIVE_URL = f"{SCOTUS_ROOT}/xmls/archive"
XML_CURRENT_URL = f"{SCOTUS_ROOT}/xmls/current"
JINA_HTTP_PREFIX = "https://r.jina.ai/http://"
WAYBACK_RAW_PREFIX = "https://web.archive.org/web/2id_/"
WAYBACK_TS_PREFIX = "https://web.archive.org/web/"
CDX_API_URL = "https://web.archive.org/cdx/search/cdx"
DEFAULT_VAULT = OBSIDIAN_ROOT

DAY_NAMES = (
    "MONDAY",
    "TUESDAY",
    "WEDNESDAY",
    "THURSDAY",
    "FRIDAY",
    "SATURDAY",
    "SUNDAY",
)
CASE_EXCLUDE_PREFIXES = ("frap", "frbk", "frcr", "frcv", "frev", "cl")

THREAD_LOCAL = threading.local()
CDX_SNAPSHOT_CACHE: dict[str, str] = {}
CDX_CACHE_LOCK = threading.Lock()
CDX_TOKEN_CACHE: dict[str, tuple[str, str]] = {}
CDX_TOKEN_CACHE_LOCK = threading.Lock()


@dataclass(frozen=True)
class XmlEntry:
    decoded_name: str
    xml_url: str
    listed_timestamp: dt.datetime


@dataclass
class ParsedMetadata:
    case_number: str
    caption: str
    decision_date: dt.date
    plain_text: str


@dataclass
class IngestRecord:
    case_id: str
    case_number: str
    caption: str
    decision_date: str
    xml_url: str
    pdf_url: str
    xml_rel_path: str
    pdf_rel_path: str
    md_rel_path: str
    pdf_found: bool
    text_source: str
    error: str | None = None


def ingest_record_from_dict(data: dict) -> IngestRecord:
    return IngestRecord(
        case_id=str(data.get("case_id", "")),
        case_number=str(data.get("case_number", "")),
        caption=str(data.get("caption", "")),
        decision_date=str(data.get("decision_date", "")),
        xml_url=str(data.get("xml_url", "")),
        pdf_url=str(data.get("pdf_url", "")),
        xml_rel_path=str(data.get("xml_rel_path", data.get("xml_path", ""))),
        pdf_rel_path=str(data.get("pdf_rel_path", data.get("pdf_path", ""))),
        md_rel_path=str(data.get("md_rel_path", data.get("md_path", ""))),
        pdf_found=bool(data.get("pdf_found", False)),
        text_source=str(data.get("text_source", "unknown")),
        error=data.get("error"),
    )


def build_session() -> requests.Session:
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        backoff_factor=0.4,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=32, pool_maxsize=64)
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Acquittify-SCOTUS-Ingest/1.0 (+https://www.supremecourt.gov/xmls/)"
        }
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def get_thread_session() -> requests.Session:
    session = getattr(THREAD_LOCAL, "session", None)
    if session is None:
        session = build_session()
        THREAD_LOCAL.session = session
    return session


def lookup_cdx_snapshot_timestamp(url: str) -> str:
    canonical_url = canonicalize_pdf_url(url)
    with CDX_CACHE_LOCK:
        cached = CDX_SNAPSHOT_CACHE.get(canonical_url)
    if cached is not None:
        return cached

    session = get_thread_session()
    candidates = [canonical_url]
    parsed = urllib.parse.urlparse(canonical_url)
    if parsed.scheme == "https":
        candidates.append(
            urllib.parse.urlunparse(("http", parsed.netloc, parsed.path, "", "", ""))
        )

    best_ts = ""
    for candidate in candidates:
        params = [
            ("url", candidate),
            ("matchType", "exact"),
            ("output", "json"),
            ("fl", "timestamp,original,statuscode,mimetype"),
            ("filter", "statuscode:200"),
            ("filter", "mimetype:application/pdf"),
        ]
        try:
            resp = session.get(CDX_API_URL, params=params, timeout=45)
        except requests.RequestException:
            continue
        if resp.status_code != 200:
            continue
        try:
            payload = resp.json()
        except ValueError:
            continue
        if not isinstance(payload, list):
            continue
        for row in payload[1:]:
            if not isinstance(row, list) or len(row) < 1:
                continue
            ts = str(row[0]).strip()
            if ts and ts > best_ts:
                best_ts = ts

    with CDX_CACHE_LOCK:
        CDX_SNAPSHOT_CACHE[canonical_url] = best_ts
    return best_ts


def lookup_cdx_pdf_url_for_token(token: str) -> tuple[str, str]:
    raw_token = (token or "").strip().lower()
    raw_token = raw_token.replace("–", "-").replace("—", "-")
    if not raw_token:
        return "", ""

    cache_key = normalize_key(raw_token) or raw_token
    with CDX_TOKEN_CACHE_LOCK:
        cached = CDX_TOKEN_CACHE.get(cache_key)
    if cached is not None:
        return cached

    session = get_thread_session()
    token_candidates = [raw_token]
    normalized_token = normalize_key(raw_token)
    if normalized_token and normalized_token not in token_candidates:
        token_candidates.append(normalized_token)

    url_ts_map: dict[str, str] = {}
    for candidate in token_candidates:
        escaped = re.escape(candidate)
        params = [
            ("url", "www.supremecourt.gov/*"),
            ("matchType", "domain"),
            ("output", "json"),
            ("fl", "timestamp,original,statuscode,mimetype"),
            ("filter", "statuscode:200"),
            ("filter", "mimetype:application/pdf"),
            ("filter", f"original:.*{escaped}.*"),
        ]
        try:
            resp = session.get(CDX_API_URL, params=params, timeout=45)
        except requests.RequestException:
            continue
        if resp.status_code != 200:
            continue
        try:
            payload = resp.json()
        except ValueError:
            continue
        if not isinstance(payload, list):
            continue

        for row in payload[1:]:
            if not isinstance(row, list) or len(row) < 2:
                continue
            timestamp = str(row[0]).strip()
            original = str(row[1]).strip()
            canonical_url = canonicalize_pdf_url(original)
            path_lc = urllib.parse.urlparse(canonical_url).path.lower()
            if not path_lc.endswith(".pdf"):
                continue
            if "/opinions/" not in path_lc and "/orders/" not in path_lc:
                continue
            prev_ts = url_ts_map.get(canonical_url)
            if prev_ts is None or timestamp > prev_ts:
                url_ts_map[canonical_url] = timestamp

    best_url = ""
    best_ts = ""
    best_score = -1
    for candidate_url, timestamp in url_ts_map.items():
        filename = urllib.parse.unquote(PurePosixPath(urllib.parse.urlparse(candidate_url).path).name)
        stem_key = normalize_key(Path(filename).stem)
        score = 0
        if normalized_token and stem_key.startswith(normalized_token):
            score += 50
        if normalized_token and normalized_token in stem_key:
            score += 10
        path_lc = urllib.parse.urlparse(candidate_url).path.lower()
        if normalized_token.endswith("zr") or normalized_token.endswith("zor"):
            if "/orders/courtorders/" in path_lc:
                score += 20
        if "-" in raw_token and "/opinions/" in path_lc:
            score += 8
        score += 2 if "?" not in candidate_url else 0
        if score > best_score or (score == best_score and timestamp > best_ts):
            best_score = score
            best_url = candidate_url
            best_ts = timestamp

    result = (best_url, best_ts) if best_url else ("", "")
    with CDX_TOKEN_CACHE_LOCK:
        CDX_TOKEN_CACHE[cache_key] = result
    return result


def normalize_key(raw: str) -> str:
    text = urllib.parse.unquote(raw or "").strip().lower()
    text = html.unescape(text)
    for dash in ("–", "—", "−", "‑", "‒"):
        text = text.replace(dash, "-")
    text = text.replace(".xml", "").replace(".pdf", "")
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[^a-z0-9-]", "", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text


def canonicalize_pdf_url(url: str) -> str:
    parsed = urllib.parse.urlparse((url or "").strip())
    scheme = "https"
    netloc = parsed.netloc.lower().replace(":80", "")
    if netloc.startswith("www."):
        host = netloc
    elif netloc == "supremecourt.gov":
        host = "www.supremecourt.gov"
    else:
        host = netloc or "www.supremecourt.gov"
    path = parsed.path or ""
    return urllib.parse.urlunparse((scheme, host, path, "", "", ""))


def build_term_codes_for_since_year(since_year: int) -> list[int]:
    today = dt.date.today()
    current_term_year = today.year if today.month >= 10 else today.year - 1
    start_term_year = max(1900, since_year - 1)
    if start_term_year > current_term_year:
        return [current_term_year % 100]
    return sorted({year % 100 for year in range(start_term_year, current_term_year + 1)})


def extract_pdf_prefix_token(stem: str) -> str:
    clean = urllib.parse.unquote(stem or "").strip()
    docket_match = re.match(r"^([0-9]{1,2}[a-z]?-[0-9]+)", clean, flags=re.IGNORECASE)
    if docket_match:
        return docket_match.group(1)
    application_match = re.match(r"^([0-9]{1,2}a[0-9]+)", clean, flags=re.IGNORECASE)
    if application_match:
        return application_match.group(1)
    return clean.split("_", 1)[0]


def jina_proxy_url(url: str) -> str:
    no_scheme = re.sub(r"^https?://", "", url.strip(), flags=re.IGNORECASE)
    return f"{JINA_HTTP_PREFIX}{no_scheme}"


def wayback_raw_url(url: str) -> str:
    return f"{WAYBACK_RAW_PREFIX}{url}"


def wayback_snapshot_url(url: str, timestamp: str) -> str:
    return f"{WAYBACK_TS_PREFIX}{timestamp}id_/{url}"


def extract_jina_markdown(text: str) -> str:
    marker = "Markdown Content:"
    idx = text.find(marker)
    if idx == -1:
        return text.strip()
    return text[idx + len(marker) :].strip()


def wrap_proxy_text_as_xml(url: str, proxy_text: str) -> str:
    safe_text = proxy_text.replace("]]>", "]]]]><![CDATA[>")
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<proxy_source source_url="{html.escape(url)}" provider="r.jina.ai">\n'
        f"  <content><![CDATA[{safe_text}]]></content>\n"
        "</proxy_source>\n"
    )


def sanitize_slug(raw: str) -> str:
    slug = normalize_key(raw)
    if slug:
        return slug
    digest = hashlib.sha1((raw or "unknown").encode("utf-8")).hexdigest()[:12]
    return f"case-{digest}"


def parse_directory_xml_entries(html_text: str) -> list[XmlEntry]:
    html_pattern = re.compile(
        r'(?P<stamp>\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}\s+[AP]M)\s+\d+\s+<A HREF="(?P<href>/xmls/(?:archive|current)/[^"]+?\.xml)">',
        flags=re.IGNORECASE,
    )
    markdown_url_pattern = re.compile(
        r"(?P<stamp>\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}\s+[AP]M)\s+\d+\s+\[[^\]]+?\.xml\]\((?P<href>https?://www\.supremecourt\.gov/xmls/(?:archive|current)/[^)]+?\.xml)\)",
        flags=re.IGNORECASE,
    )
    markdown_name_pattern = re.compile(
        r"(?P<stamp>\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}\s+[AP]M)\s+\d+\s+\[(?P<name>[^\]]+?\.xml)\]\((?P<href>https?://www\.supremecourt\.gov/xmls/(?:archive|current)/?)\)",
        flags=re.IGNORECASE,
    )
    entries: dict[str, XmlEntry] = {}

    def upsert_entry(stamp_str: str, href: str, explicit_name: str = "") -> None:
        listed_ts = dt.datetime.strptime(stamp_str, "%m/%d/%Y %I:%M %p")
        if explicit_name:
            filename_encoded = urllib.parse.quote(explicit_name)
            href_base = href.rstrip("/") + "/"
            xml_url = urllib.parse.urljoin(href_base, filename_encoded)
            decoded_name = explicit_name
        elif href.startswith("http://") or href.startswith("https://"):
            xml_url = href
            filename_encoded = urllib.parse.urlparse(href).path.rsplit("/", 1)[-1]
            decoded_name = urllib.parse.unquote(filename_encoded)
        else:
            xml_url = urllib.parse.urljoin(SCOTUS_ROOT, href)
            filename_encoded = href.rsplit("/", 1)[-1]
            decoded_name = urllib.parse.unquote(filename_encoded)

        existing = entries.get(decoded_name.lower())
        candidate = XmlEntry(
            decoded_name=decoded_name,
            xml_url=xml_url,
            listed_timestamp=listed_ts,
        )
        if existing is None or candidate.listed_timestamp > existing.listed_timestamp:
            entries[decoded_name.lower()] = candidate

    for match in html_pattern.finditer(html_text):
        upsert_entry(match.group("stamp"), match.group("href"))
    for match in markdown_url_pattern.finditer(html_text):
        upsert_entry(match.group("stamp"), match.group("href"))
    for match in markdown_name_pattern.finditer(html_text):
        upsert_entry(match.group("stamp"), match.group("href"), explicit_name=match.group("name"))

    return sorted(entries.values(), key=lambda x: (x.listed_timestamp, x.decoded_name))


def fetch_html(session: requests.Session, url: str) -> str:
    try:
        resp = session.get(url, timeout=60)
    except requests.RequestException:
        resp = None
    if resp is not None and resp.status_code == 200:
        return resp.text

    # Fallback through jina proxy when origin blocks direct access.
    try:
        proxy_resp = session.get(jina_proxy_url(url), timeout=90)
    except requests.RequestException:
        return ""
    if proxy_resp.status_code != 200:
        return ""
    return proxy_resp.text


def collect_xml_entries(session: requests.Session) -> list[XmlEntry]:
    combined: dict[str, XmlEntry] = {}
    for url in (XML_ARCHIVE_URL, XML_CURRENT_URL):
        html_text = fetch_html(session, url)
        if not html_text:
            continue
        for entry in parse_directory_xml_entries(html_text):
            key = entry.decoded_name.lower()
            existing = combined.get(key)
            if existing is None or entry.listed_timestamp > existing.listed_timestamp:
                combined[key] = entry
    return sorted(combined.values(), key=lambda x: (x.listed_timestamp, x.decoded_name))


def collect_pdf_index(
    session: requests.Session,
    terms: Iterable[int],
) -> tuple[dict[str, list[str]], dict[str, list[str]], list[tuple[str, str]]]:
    pages: list[str] = [
        f"{SCOTUS_ROOT}/opinions/in-chambers.aspx",
        f"{SCOTUS_ROOT}/orders/ordersbycircuit.aspx",
        f"{SCOTUS_ROOT}/orders/grantednotedlists.aspx",
        f"{SCOTUS_ROOT}/orders/journal.aspx",
    ]
    for term in sorted({int(t) for t in terms}):
        t = f"{term:02d}"
        pages.append(f"{SCOTUS_ROOT}/opinions/slipopinion/{t}")
        pages.append(f"{SCOTUS_ROOT}/opinions/relatingtoorders/{t}")
        pages.append(f"{SCOTUS_ROOT}/orders/ordersofthecourt/{t}")

    href_pattern = re.compile(r'href=["\']([^"\']+?\.pdf)["\']', flags=re.IGNORECASE)
    markdown_pattern = re.compile(
        r"\[[^\]]+\]\((https?://[^)]+?\.pdf)\)",
        flags=re.IGNORECASE,
    )
    by_prefix: dict[str, list[str]] = {}
    by_full_stem: dict[str, list[str]] = {}
    all_index: list[tuple[str, str]] = []
    seen_urls: set[str] = set()

    for page in pages:
        html_text = fetch_html(session, page)
        if not html_text:
            continue
        matches: list[str] = []
        for match in href_pattern.finditer(html_text):
            matches.append(html.unescape(match.group(1)))
        for match in markdown_pattern.finditer(html_text):
            matches.append(html.unescape(match.group(1)))

        for href in matches:
            raw_url = urllib.parse.urljoin(page, href)
            pdf_url = canonicalize_pdf_url(raw_url)
            if pdf_url in seen_urls:
                continue
            seen_urls.add(pdf_url)
            filename = urllib.parse.unquote(PurePosixPath(urllib.parse.urlparse(pdf_url).path).name)
            stem = Path(filename).stem
            prefix = extract_pdf_prefix_token(stem)
            prefix_key = normalize_key(prefix)
            full_key = normalize_key(stem)
            if prefix_key:
                by_prefix.setdefault(prefix_key, []).append(pdf_url)
                all_index.append((prefix_key, pdf_url))
            if full_key:
                by_full_stem.setdefault(full_key, []).append(pdf_url)
    return by_prefix, by_full_stem, all_index


def collect_cdx_pdf_index(
    session: requests.Session,
    terms: Iterable[int],
) -> tuple[dict[str, list[str]], dict[str, list[str]], list[tuple[str, str]], dict[str, str]]:
    by_prefix: dict[str, list[str]] = {}
    by_full_stem: dict[str, list[str]] = {}
    all_index: list[tuple[str, str]] = []
    snapshot_ts_by_url: dict[str, str] = {}
    seen_urls: set[str] = set()

    for term in sorted({int(term) % 100 for term in terms}):
        term_code = f"{term:02d}"
        prefix_url = f"{SCOTUS_ROOT}/opinions/{term_code}pdf/"
        params = [
            ("url", prefix_url),
            ("matchType", "prefix"),
            ("output", "json"),
            ("fl", "timestamp,original,statuscode,mimetype"),
            ("filter", "statuscode:200"),
            ("filter", "mimetype:application/pdf"),
        ]
        try:
            resp = session.get(CDX_API_URL, params=params, timeout=120)
        except requests.RequestException:
            continue
        if resp.status_code != 200:
            continue

        try:
            payload = resp.json()
        except ValueError:
            continue
        if not isinstance(payload, list):
            continue

        for row in payload[1:]:
            if not isinstance(row, list) or len(row) < 2:
                continue
            timestamp = str(row[0]).strip()
            original_url = str(row[1]).strip()
            if not original_url:
                continue
            pdf_url = canonicalize_pdf_url(original_url)
            path_lc = urllib.parse.urlparse(pdf_url).path.lower()
            if not path_lc.endswith(".pdf"):
                continue
            if f"/opinions/{term_code}pdf/" not in path_lc:
                continue

            prev_ts = snapshot_ts_by_url.get(pdf_url)
            if prev_ts is None or timestamp > prev_ts:
                snapshot_ts_by_url[pdf_url] = timestamp

            if pdf_url in seen_urls:
                continue
            seen_urls.add(pdf_url)

            filename = urllib.parse.unquote(PurePosixPath(path_lc).name)
            stem = Path(filename).stem
            prefix = extract_pdf_prefix_token(stem)
            prefix_key = normalize_key(prefix)
            full_key = normalize_key(stem)
            if prefix_key:
                by_prefix.setdefault(prefix_key, []).append(pdf_url)
                all_index.append((prefix_key, pdf_url))
            if full_key:
                by_full_stem.setdefault(full_key, []).append(pdf_url)

    return by_prefix, by_full_stem, all_index, snapshot_ts_by_url


def merge_pdf_indexes(
    index_sets: Iterable[tuple[dict[str, list[str]], dict[str, list[str]], list[tuple[str, str]]]],
) -> tuple[dict[str, list[str]], dict[str, list[str]], list[tuple[str, str]]]:
    merged_by_prefix: dict[str, list[str]] = {}
    merged_by_full: dict[str, list[str]] = {}
    merged_all: list[tuple[str, str]] = []
    seen_all_pairs: set[tuple[str, str]] = set()

    for by_prefix, by_full, all_index in index_sets:
        for key, urls in by_prefix.items():
            bucket = merged_by_prefix.setdefault(key, [])
            for url in urls:
                if url not in bucket:
                    bucket.append(url)
        for key, urls in by_full.items():
            bucket = merged_by_full.setdefault(key, [])
            for url in urls:
                if url not in bucket:
                    bucket.append(url)
        for key, url in all_index:
            pair = (key, url)
            if pair in seen_all_pairs:
                continue
            seen_all_pairs.add(pair)
            merged_all.append(pair)

    return merged_by_prefix, merged_by_full, merged_all


def is_case_like_xml(name: str) -> bool:
    stem = normalize_key(Path(name).stem)
    if not stem:
        return False
    if stem.startswith(CASE_EXCLUDE_PREFIXES):
        return False
    return True


def parse_date_text(candidate: str) -> dt.date | None:
    cleaned = re.sub(r"\s+", " ", candidate.strip())
    if not cleaned:
        return None
    cleaned = cleaned.replace("Sept.", "September").replace("Sept", "September")
    cleaned = cleaned.replace("Oct.", "October").replace("Oct", "October")
    cleaned = cleaned.replace("Nov.", "November").replace("Nov", "November")
    cleaned = cleaned.replace("Dec.", "December").replace("Dec", "December")
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return dt.datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def compress_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_xml_plain_text(xml_content: str) -> tuple[str, list[str]]:
    case_numbers: list[str] = []
    paragraphs: list[str] = []

    try:
        root = ET.fromstring(xml_content)
        for node in root.iter():
            if node.tag.lower().endswith("document"):
                case_number = (node.attrib.get("CaseNumber") or "").strip()
                if case_number:
                    case_numbers.append(case_number)
            if node.tag.lower().endswith("p"):
                text = compress_whitespace("".join(node.itertext()))
                if text:
                    paragraphs.append(text)
        if paragraphs:
            return "\n".join(paragraphs), case_numbers
    except ET.ParseError:
        pass

    # Fallback for malformed XML.
    case_numbers.extend(re.findall(r'CaseNumber="([^"]+)"', xml_content))
    stripped = re.sub(r"<[^>]+>", " ", xml_content)
    stripped = html.unescape(stripped)
    stripped = re.sub(r"[ \t]+", " ", stripped)
    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    return "\n".join(lines), case_numbers


def extract_decision_date(text: str, fallback_ts: dt.datetime) -> dt.date:
    patterns = [
        re.compile(r"Decided\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})", flags=re.IGNORECASE),
        re.compile(
            rf"(?:{'|'.join(DAY_NAMES)})\s*,\s*([A-Za-z]+\s+\d{{1,2}},\s+\d{{4}})",
            flags=re.IGNORECASE,
        ),
    ]
    for pattern in patterns:
        match = pattern.search(text)
        if not match:
            continue
        parsed = parse_date_text(match.group(1))
        if parsed is not None:
            return parsed

    # Split "Dated this ... day of Month, Year."
    dated_match = re.search(
        r"Dated this\s+\d{1,2}(?:st|nd|rd|th)?\s+day of\s+([A-Za-z]+)\s*,?\s*(\d{4})",
        text,
        flags=re.IGNORECASE,
    )
    if dated_match:
        parsed = parse_date_text(f"{dated_match.group(1)} 1, {dated_match.group(2)}")
        if parsed is not None:
            # Keep month/year from order text and fallback day to listing day.
            return dt.date(parsed.year, parsed.month, min(fallback_ts.day, 28))

    return fallback_ts.date()


def extract_case_number(text: str, xml_case_numbers: list[str], source_name: str) -> str:
    for candidate in xml_case_numbers:
        cleaned = compress_whitespace(candidate)
        if cleaned:
            return cleaned

    no_match = re.search(
        r"\bNo\.?\s*([0-9]{1,2}\s*[A-Za-z]?\s*[0-9A-Za-z\-–]+)\b",
        text,
        flags=re.IGNORECASE,
    )
    if no_match:
        return compress_whitespace(no_match.group(1)).replace("–", "-")

    return Path(source_name).stem


def extract_caption(text: str, fallback: str) -> str:
    lines = [compress_whitespace(line) for line in text.splitlines() if compress_whitespace(line)]
    for line in lines[:140]:
        if len(line) > 220:
            continue
        if "cite as:" in line.lower():
            continue
        if re.search(r"\bv\.\b", line, flags=re.IGNORECASE):
            return line
    return fallback


def parse_xml_metadata(xml_content: str, source_name: str, listed_ts: dt.datetime) -> ParsedMetadata:
    plain_text, case_numbers = extract_xml_plain_text(xml_content)
    decision_date = extract_decision_date(plain_text, listed_ts)
    case_number = extract_case_number(plain_text, case_numbers, source_name)
    caption = extract_caption(plain_text, case_number)
    return ParsedMetadata(
        case_number=case_number,
        caption=caption,
        decision_date=decision_date,
        plain_text=plain_text,
    )


def resolve_pdf_url(
    source_name: str,
    case_number: str,
    by_prefix: dict[str, list[str]],
    by_full_stem: dict[str, list[str]],
    all_index: list[tuple[str, str]],
) -> str:
    stem = Path(source_name).stem
    keys = []
    for candidate in (stem, case_number):
        key = normalize_key(candidate)
        if key:
            keys.append(key)
            keys.append(re.sub(r"new\d+$", "", key))
            keys.append(re.sub(r"\d+$", "", key))

    checked: set[str] = set()
    for key in keys:
        if not key or key in checked:
            continue
        checked.add(key)
        if key in by_full_stem and by_full_stem[key]:
            return by_full_stem[key][0]
        if key in by_prefix and by_prefix[key]:
            return by_prefix[key][0]

    # Fuzzy prefix fallback for variations like "24-154new2" vs "24-154".
    fuzzy_candidates: list[tuple[int, str]] = []
    for key in keys:
        if len(key) < 5:
            continue
        for index_key, url in all_index:
            if index_key.startswith(key) or key.startswith(index_key):
                score = abs(len(index_key) - len(key))
                fuzzy_candidates.append((score, url))
    if fuzzy_candidates:
        fuzzy_candidates.sort(key=lambda x: x[0])
        return fuzzy_candidates[0][1]
    return ""


def download_text(url: str) -> str:
    session = get_thread_session()
    try:
        resp = session.get(url, timeout=90)
    except requests.RequestException:
        resp = None
    if resp is not None and resp.status_code == 200:
        return resp.text

    proxy_url = jina_proxy_url(url)
    proxy_resp = session.get(proxy_url, timeout=120)
    proxy_resp.raise_for_status()
    proxy_text = extract_jina_markdown(proxy_resp.text)
    if url.lower().endswith(".xml"):
        return wrap_proxy_text_as_xml(url, proxy_text)
    return proxy_text


def download_binary(
    url: str,
    target_path: Path,
    snapshot_ts_by_url: dict[str, str] | None = None,
) -> bool:
    session = get_thread_session()
    canonical_url = canonicalize_pdf_url(url)
    candidate_urls: list[str] = []
    for candidate in (url, canonical_url):
        if candidate and candidate not in candidate_urls:
            candidate_urls.append(candidate)
    timestamp = ""
    if snapshot_ts_by_url:
        timestamp = snapshot_ts_by_url.get(canonical_url, "")
    if not timestamp:
        timestamp = lookup_cdx_snapshot_timestamp(canonical_url)
    if timestamp:
        snapshot_url = wayback_snapshot_url(canonical_url, timestamp)
        if snapshot_url not in candidate_urls:
            candidate_urls.append(snapshot_url)
    raw_wayback_url = wayback_raw_url(canonical_url)
    if raw_wayback_url not in candidate_urls:
        candidate_urls.append(raw_wayback_url)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    for candidate_url in candidate_urls:
        try:
            resp = session.get(candidate_url, timeout=180, stream=True, allow_redirects=True)
        except requests.RequestException:
            continue
        if resp.status_code != 200:
            continue

        tmp_path = target_path.with_suffix(target_path.suffix + ".part")
        with tmp_path.open("wb") as file_obj:
            for chunk in resp.iter_content(chunk_size=256 * 1024):
                if chunk:
                    file_obj.write(chunk)

        # Validate PDF header when downloading .pdf files.
        if target_path.suffix.lower() == ".pdf":
            try:
                with tmp_path.open("rb") as file_obj:
                    header = file_obj.read(5)
                if header != b"%PDF-":
                    tmp_path.unlink(missing_ok=True)
                    continue
            except OSError:
                tmp_path.unlink(missing_ok=True)
                continue

        tmp_path.replace(target_path)
        return True

    return False


def extract_pdf_text(pdf_path: Path) -> str:
    cmd = ["pdftotext", "-layout", "-enc", "UTF-8", str(pdf_path), "-"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode == 0:
        return result.stdout.strip()
    return ""


def safe_yaml_text(raw: str) -> str:
    return raw.replace("\\", "\\\\").replace('"', '\\"')


def write_markdown_note(
    md_path: Path,
    case_id: str,
    metadata: ParsedMetadata,
    xml_url: str,
    pdf_url: str,
    xml_rel: Path,
    pdf_rel: Path,
    pdf_exists: bool,
    text_source: str,
    extracted_text: str,
) -> None:
    frontmatter_lines = [
        "---",
        f'case_id: "{safe_yaml_text(case_id)}"',
        f'case_number: "{safe_yaml_text(metadata.case_number)}"',
        f'caption: "{safe_yaml_text(metadata.caption)}"',
        f'decision_date: "{metadata.decision_date.isoformat()}"',
        'source: "supreme_court_xml"',
        f'xml_url: "{safe_yaml_text(xml_url)}"',
        f'pdf_url: "{safe_yaml_text(pdf_url)}"',
        f'xml_file: "{safe_yaml_text(xml_rel.as_posix())}"',
        f'pdf_file: "{safe_yaml_text(pdf_rel.as_posix())}"',
        f'extracted_text_source: "{safe_yaml_text(text_source)}"',
        "tags:",
        "  - scotus",
        "  - case",
        "---",
        "",
    ]
    body_lines = [
        f"# {metadata.caption}",
        "",
        f"- Case Number: `{metadata.case_number}`",
        f"- Decision Date: `{metadata.decision_date.isoformat()}`",
        f"- Native PDF: `[[{pdf_rel.name}]]`" if pdf_exists else "- Native PDF: `missing`",
        f"- Source XML: `[[{xml_rel.name}]]`",
        "",
        "## Extracted Text",
        "",
        extracted_text.strip() if extracted_text.strip() else "_No extracted text available._",
        "",
    ]
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(frontmatter_lines + body_lines), encoding="utf-8")


def should_skip_for_since_date(decision_date: dt.date, since_year: int) -> bool:
    return decision_date < dt.date(since_year, 1, 1)


def process_entry(
    entry: XmlEntry,
    vault_path: Path,
    since_year: int,
    refresh: bool,
    by_prefix: dict[str, list[str]],
    by_full_stem: dict[str, list[str]],
    all_index: list[tuple[str, str]],
    snapshot_ts_by_url: dict[str, str] | None = None,
) -> IngestRecord | None:
    if not is_case_like_xml(entry.decoded_name):
        return None

    xml_text = download_text(entry.xml_url)
    metadata = parse_xml_metadata(xml_text, entry.decoded_name, entry.listed_timestamp)
    if should_skip_for_since_date(metadata.decision_date, since_year):
        return None

    stem_slug = sanitize_slug(Path(entry.decoded_name).stem)
    case_id = f"SCOTUS-{stem_slug}"
    year_folder = str(metadata.decision_date.year)
    case_dir = vault_path / "Cases" / year_folder / stem_slug
    case_dir.mkdir(parents=True, exist_ok=True)

    xml_path = case_dir / f"{stem_slug}.xml"
    pdf_path = case_dir / f"{stem_slug}.pdf"
    md_path = case_dir / f"{stem_slug}.md"

    if refresh or not xml_path.exists():
        xml_path.write_text(xml_text, encoding="utf-8")

    pdf_url = resolve_pdf_url(
        source_name=entry.decoded_name,
        case_number=metadata.case_number,
        by_prefix=by_prefix,
        by_full_stem=by_full_stem,
        all_index=all_index,
    )
    if not pdf_url:
        token_candidates = [
            Path(entry.decoded_name).stem,
            metadata.case_number,
            metadata.caption,
        ]
        for token in token_candidates:
            candidate_url, candidate_ts = lookup_cdx_pdf_url_for_token(token)
            if not candidate_url:
                continue
            pdf_url = candidate_url
            if snapshot_ts_by_url is not None and candidate_ts:
                prev_ts = snapshot_ts_by_url.get(candidate_url, "")
                if not prev_ts or candidate_ts > prev_ts:
                    snapshot_ts_by_url[candidate_url] = candidate_ts
            break

    pdf_found = False
    if pdf_url:
        if refresh or not pdf_path.exists():
            pdf_found = download_binary(pdf_url, pdf_path, snapshot_ts_by_url=snapshot_ts_by_url)
        else:
            pdf_found = True
    text_source = "xml"
    extracted_text = metadata.plain_text
    if pdf_found and pdf_path.exists():
        pdf_text = extract_pdf_text(pdf_path)
        if pdf_text.strip():
            extracted_text = pdf_text
            text_source = "pdf"

    xml_rel = xml_path.relative_to(vault_path)
    pdf_rel = pdf_path.relative_to(vault_path)
    md_rel = md_path.relative_to(vault_path)

    write_markdown_note(
        md_path=md_path,
        case_id=case_id,
        metadata=metadata,
        xml_url=entry.xml_url,
        pdf_url=pdf_url,
        xml_rel=xml_rel,
        pdf_rel=pdf_rel,
        pdf_exists=pdf_found and pdf_path.exists(),
        text_source=text_source,
        extracted_text=extracted_text,
    )

    return IngestRecord(
        case_id=case_id,
        case_number=metadata.case_number,
        caption=metadata.caption,
        decision_date=metadata.decision_date.isoformat(),
        xml_url=entry.xml_url,
        pdf_url=pdf_url,
        xml_rel_path=xml_rel.as_posix(),
        pdf_rel_path=pdf_rel.as_posix(),
        md_rel_path=md_rel.as_posix(),
        pdf_found=pdf_found and pdf_path.exists(),
        text_source=text_source,
    )


def write_manifests(vault_path: Path, records: Iterable[IngestRecord]) -> dict[str, int]:
    ontology_dir = vault_path / "Ontology"
    ontology_dir.mkdir(parents=True, exist_ok=True)
    unique_by_note_path: dict[str, IngestRecord] = {}
    for record in records:
        key = record.md_rel_path
        existing = unique_by_note_path.get(key)
        if existing is None:
            unique_by_note_path[key] = record
            continue
        # Prefer rows with native PDF when duplicate note entries exist.
        if record.pdf_found and not existing.pdf_found:
            unique_by_note_path[key] = record

    records_sorted = sorted(unique_by_note_path.values(), key=lambda r: (r.decision_date, r.case_id))

    csv_path = ontology_dir / "supreme_court_case_file_links.csv"
    jsonl_path = ontology_dir / "supreme_court_case_file_links.jsonl"

    headers = [
        "case_id",
        "case_number",
        "caption",
        "decision_date",
        "xml_url",
        "pdf_url",
        "xml_path",
        "pdf_path",
        "md_path",
        "pdf_found",
        "text_source",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=headers)
        writer.writeheader()
        for record in records_sorted:
            writer.writerow(
                {
                    "case_id": record.case_id,
                    "case_number": record.case_number,
                    "caption": record.caption,
                    "decision_date": record.decision_date,
                    "xml_url": record.xml_url,
                    "pdf_url": record.pdf_url,
                    "xml_path": record.xml_rel_path,
                    "pdf_path": record.pdf_rel_path,
                    "md_path": record.md_rel_path,
                    "pdf_found": record.pdf_found,
                    "text_source": record.text_source,
                }
            )

    with jsonl_path.open("w", encoding="utf-8") as jsonl_file:
        for record in records_sorted:
            jsonl_file.write(json.dumps(record.__dict__, ensure_ascii=False) + "\n")

    total = len(records_sorted)
    with_pdf = sum(1 for r in records_sorted if r.pdf_found)
    no_pdf = total - with_pdf
    return {"total": total, "with_pdf": with_pdf, "missing_pdf": no_pdf}


def build_ontology_db(vault_path: Path, records: Iterable[IngestRecord]) -> Path:
    db_path = vault_path / ".ponner" / "federation.sqlite3"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS ontology_objects (
            object_id TEXT PRIMARY KEY,
            object_type TEXT NOT NULL,
            name TEXT NOT NULL,
            note_path TEXT NOT NULL UNIQUE,
            taxonomy_codes TEXT NOT NULL,
            metadata TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ontology_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_object_id TEXT NOT NULL,
            predicate TEXT NOT NULL,
            target_object_id TEXT NOT NULL,
            evidence_path TEXT NOT NULL,
            evidence_snippet TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(source_object_id, predicate, target_object_id, evidence_path, evidence_snippet)
        );
        CREATE TABLE IF NOT EXISTS ontology_lineage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            input_ref TEXT NOT NULL,
            output_ref TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ontology_objects_note_path
            ON ontology_objects(note_path);
        CREATE INDEX IF NOT EXISTS idx_ontology_links_source
            ON ontology_links(source_object_id);
        CREATE INDEX IF NOT EXISTS idx_ontology_links_target
            ON ontology_links(target_object_id);
        """
    )
    cur.execute("DELETE FROM ontology_links")
    cur.execute("DELETE FROM ontology_objects")
    cur.execute("DELETE FROM ontology_lineage")

    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    run_id = f"scotus-ingest-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

    records_list_raw = list(records)
    records_list: list[IngestRecord] = []
    seen_note_paths: set[str] = set()
    for record in records_list_raw:
        if record.md_rel_path in seen_note_paths:
            continue
        seen_note_paths.add(record.md_rel_path)
        records_list.append(record)

    for record in records_list:
        stable_token = hashlib.sha1(record.md_rel_path.encode("utf-8")).hexdigest()[:12]
        case_object_id = f"case::{record.case_id}::{stable_token}"
        case_meta = {
            "case_number": record.case_number,
            "caption": record.caption,
            "decision_date": record.decision_date,
            "xml_url": record.xml_url,
            "pdf_url": record.pdf_url,
            "xml_path": record.xml_rel_path,
            "pdf_path": record.pdf_rel_path,
            "md_path": record.md_rel_path,
            "text_source": record.text_source,
        }
        cur.execute(
            """
            INSERT INTO ontology_objects (
                object_id, object_type, name, note_path, taxonomy_codes, metadata, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                case_object_id,
                "AQ.CASE",
                record.caption,
                record.md_rel_path,
                json.dumps(["AQ.CASE", "SCOTUS"], ensure_ascii=False),
                json.dumps(case_meta, ensure_ascii=False),
                now_iso,
                now_iso,
            ),
        )

        if record.pdf_found:
            pdf_object_id = f"doc::{record.case_id}::{stable_token}::pdf"
            pdf_meta = {
                "case_id": record.case_id,
                "source": "supreme_court_pdf",
                "pdf_url": record.pdf_url,
                "file_path": record.pdf_rel_path,
            }
            cur.execute(
                """
                INSERT INTO ontology_objects (
                    object_id, object_type, name, note_path, taxonomy_codes, metadata, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pdf_object_id,
                    "AQ.DOCUMENT",
                    f"{record.caption} (Native PDF)",
                    record.pdf_rel_path,
                    json.dumps(["AQ.DOCUMENT", "SCOTUS"], ensure_ascii=False),
                    json.dumps(pdf_meta, ensure_ascii=False),
                    now_iso,
                    now_iso,
                ),
            )
            cur.execute(
                """
                INSERT INTO ontology_links (
                    source_object_id, predicate, target_object_id, evidence_path, evidence_snippet, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    case_object_id,
                    "AQ.HAS_NATIVE_FILE",
                    pdf_object_id,
                    record.md_rel_path,
                    f"native_pdf={record.pdf_rel_path}",
                    now_iso,
                ),
            )

    payload = {
        "records": len(records_list),
        "pdf_linked_records": sum(1 for r in records_list if r.pdf_found),
    }
    cur.execute(
        """
        INSERT INTO ontology_lineage (
            run_id, event_type, input_ref, output_ref, payload, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            "ingest_summary",
            "supreme_court_xml",
            ".ponner/federation.sqlite3",
            json.dumps(payload, ensure_ascii=False),
            now_iso,
        ),
    )

    conn.commit()
    conn.close()
    return db_path


def write_summary(vault_path: Path, summary: dict[str, int], elapsed_seconds: float) -> Path:
    summary_path = vault_path / "Ontology" / "ingest_summary.json"
    payload = {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "elapsed_seconds": round(elapsed_seconds, 3),
        "total_cases_ingested": summary["total"],
        "cases_with_native_pdf": summary["with_pdf"],
        "cases_missing_pdf": summary["missing_pdf"],
        "vault_path": str(vault_path),
    }
    summary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return summary_path


def load_existing_manifest_records(vault_path: Path) -> list[IngestRecord]:
    manifest_path = vault_path / "Ontology" / "supreme_court_case_file_links.jsonl"
    if not manifest_path.exists():
        return []
    records: list[IngestRecord] = []
    for line in manifest_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        record = ingest_record_from_dict(payload)
        if record.xml_url:
            records.append(record)
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest SCOTUS XML cases into an Obsidian vault with native PDFs and Markdown text."
    )
    parser.add_argument(
        "--vault-path",
        default=str(DEFAULT_VAULT),
        help=f'Vault directory path (default: "{DEFAULT_VAULT}")',
    )
    parser.add_argument(
        "--since-year",
        type=int,
        default=1995,
        help="Only ingest cases with decision date on/after Jan 1 of this year.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=max(4, (os.cpu_count() or 8) // 2),
        help="Parallel workers for downloads/extraction.",
    )
    parser.add_argument(
        "--max-term",
        type=int,
        default=30,
        help="Maximum numeric term suffix to scrape for PDF indexes.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-download and re-write existing files.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional cap on XML entries processed (0 = no limit).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    start_time = dt.datetime.now(dt.timezone.utc)
    vault_path = Path(args.vault_path).expanduser().resolve()
    vault_path.mkdir(parents=True, exist_ok=True)

    bootstrap_session = build_session()
    xml_entries = collect_xml_entries(bootstrap_session)
    if args.limit and args.limit > 0:
        xml_entries = xml_entries[: args.limit]
    print(f"Collected XML entries: {len(xml_entries)}")

    required_terms = build_term_codes_for_since_year(args.since_year)
    live_terms = sorted(set(required_terms).union(set(range(args.max_term + 1))))
    live_by_prefix, live_by_full_stem, live_all_index = collect_pdf_index(
        bootstrap_session,
        terms=live_terms,
    )
    print(
        "Indexed live PDF links:",
        f"prefix_keys={len(live_by_prefix)}",
        f"full_keys={len(live_by_full_stem)}",
        f"entries={len(live_all_index)}",
        f"terms={len(live_terms)}",
    )

    cdx_by_prefix, cdx_by_full_stem, cdx_all_index, snapshot_ts_by_url = collect_cdx_pdf_index(
        bootstrap_session,
        terms=required_terms,
    )
    print(
        "Indexed archived PDF links (CDX):",
        f"prefix_keys={len(cdx_by_prefix)}",
        f"full_keys={len(cdx_by_full_stem)}",
        f"entries={len(cdx_all_index)}",
        f"snapshots={len(snapshot_ts_by_url)}",
        f"terms={len(required_terms)}",
    )

    by_prefix, by_full_stem, all_index = merge_pdf_indexes(
        [
            (live_by_prefix, live_by_full_stem, live_all_index),
            (cdx_by_prefix, cdx_by_full_stem, cdx_all_index),
        ]
    )
    print(
        "Merged PDF index:",
        f"prefix_keys={len(by_prefix)}",
        f"full_keys={len(by_full_stem)}",
        f"entries={len(all_index)}",
    )

    records: list[IngestRecord] = []
    errors: list[str] = []
    existing_by_xml_url: dict[str, IngestRecord] = {}
    if not args.refresh:
        for record in load_existing_manifest_records(vault_path):
            existing_by_xml_url[record.xml_url] = record
        if existing_by_xml_url:
            print(f"Loaded existing manifest records: {len(existing_by_xml_url)}")

    entries_to_process: list[XmlEntry] = []
    reused_complete = 0
    repair_candidates = 0
    for entry in xml_entries:
        existing = existing_by_xml_url.get(entry.xml_url)
        if existing is None or args.refresh:
            entries_to_process.append(entry)
            continue

        xml_exists = bool(existing.xml_rel_path) and (vault_path / existing.xml_rel_path).exists()
        md_exists = bool(existing.md_rel_path) and (vault_path / existing.md_rel_path).exists()
        pdf_exists = (not existing.pdf_found) or (
            bool(existing.pdf_rel_path) and (vault_path / existing.pdf_rel_path).exists()
        )

        if existing.pdf_found and xml_exists and md_exists and pdf_exists:
            records.append(existing)
            reused_complete += 1
            continue

        repair_candidates += 1
        entries_to_process.append(entry)

    if reused_complete:
        print(f"Reused complete records: {reused_complete}")
    if repair_candidates:
        print(f"Queued records for repair/retry: {repair_candidates}")
    completed = 0
    total = len(entries_to_process)

    if total == 0:
        print("No new XML entries to process; rebuilding manifests and ontology only.")
        summary = write_manifests(vault_path, records)
        db_path = build_ontology_db(vault_path, records)
        elapsed = (dt.datetime.now(dt.timezone.utc) - start_time).total_seconds()
        summary_path = write_summary(vault_path, summary, elapsed)
        print(f"Vault: {vault_path}")
        print(f"Ontology DB: {db_path}")
        print(f"Summary: {summary_path}")
        print(
            "Counts:",
            f"total={summary['total']}",
            f"with_pdf={summary['with_pdf']}",
            f"missing_pdf={summary['missing_pdf']}",
        )
        print(f"Elapsed seconds: {elapsed:.2f}")
        return 0

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        future_map = {
            executor.submit(
                process_entry,
                entry,
                vault_path,
                args.since_year,
                args.refresh,
                by_prefix,
                by_full_stem,
                all_index,
                snapshot_ts_by_url,
            ): entry
            for entry in entries_to_process
        }
        for future in as_completed(future_map):
            completed += 1
            entry = future_map[future]
            try:
                record = future.result()
                if record is not None:
                    records.append(record)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                errors.append(f"{entry.decoded_name}: {exc}")
            if completed % 25 == 0 or completed == total:
                print(f"Progress: {completed}/{total} complete, ingested={len(records)}, errors={len(errors)}")

    summary = write_manifests(vault_path, records)
    db_path = build_ontology_db(vault_path, records)
    elapsed = (dt.datetime.now(dt.timezone.utc) - start_time).total_seconds()
    summary_path = write_summary(vault_path, summary, elapsed)

    if errors:
        errors_path = vault_path / "Ontology" / "ingest_errors.log"
        errors_path.write_text("\n".join(errors), encoding="utf-8")
        print(f"Wrote errors: {errors_path} ({len(errors)})")

    print(f"Vault: {vault_path}")
    print(f"Ontology DB: {db_path}")
    print(f"Summary: {summary_path}")
    print(
        "Counts:",
        f"total={summary['total']}",
        f"with_pdf={summary['with_pdf']}",
        f"missing_pdf={summary['missing_pdf']}",
    )
    print(f"Elapsed seconds: {elapsed:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
