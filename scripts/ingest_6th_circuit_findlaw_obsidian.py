#!/usr/bin/env python3
"""Ingest FindLaw federal circuit cases into an Obsidian-style vault.

This script:
1) Crawls year pages for a selected US federal circuit from FindLaw (2010+ by default).
2) Uses a conservative, throttled request cadence to limit local network impact.
3) Stores source case markdown + normalized case notes under Cases/<year>/<case_slug>/.
4) Writes ontology manifests and a lightweight federation DB under the vault.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import random
import re
import sqlite3
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

JINA_HTTP_PREFIX = "https://r.jina.ai/http://"
DEFAULT_TIMEOUT_SECONDS = 60
OBSIDIAN_DOCUMENTS_ROOT = (
    Path.home()
    / "Library"
    / "Mobile Documents"
    / "iCloud~md~obsidian"
    / "Documents"
)

CIRCUIT_PROFILES: dict[str, dict[str, str]] = {
    "us-dc-circuit": {
        "vault_name": "D.C. Circuit",
        "display_name": "D.C. Circuit",
        "court_code": "USDC",
        "court_tag": "dc-circuit",
        "source_id": "findlaw_us_dc_circuit",
        "manifest_prefix": "dc_circuit",
    },
    "us-1st-circuit": {
        "vault_name": "1st Circuit",
        "display_name": "1st Circuit",
        "court_code": "US1C",
        "court_tag": "first-circuit",
        "source_id": "findlaw_us_1st_circuit",
        "manifest_prefix": "first_circuit",
    },
    "us-2nd-circuit": {
        "vault_name": "2nd Circuit",
        "display_name": "2nd Circuit",
        "court_code": "US2C",
        "court_tag": "second-circuit",
        "source_id": "findlaw_us_2nd_circuit",
        "manifest_prefix": "second_circuit",
    },
    "us-3rd-circuit": {
        "vault_name": "3rd Circuit",
        "display_name": "3rd Circuit",
        "court_code": "US3C",
        "court_tag": "third-circuit",
        "source_id": "findlaw_us_3rd_circuit",
        "manifest_prefix": "third_circuit",
    },
    "us-4th-circuit": {
        "vault_name": "4th Circuit",
        "display_name": "4th Circuit",
        "court_code": "US4C",
        "court_tag": "fourth-circuit",
        "source_id": "findlaw_us_4th_circuit",
        "manifest_prefix": "fourth_circuit",
    },
    "us-5th-circuit": {
        "vault_name": "5th Circuit",
        "display_name": "5th Circuit",
        "court_code": "US5C",
        "court_tag": "fifth-circuit",
        "source_id": "findlaw_us_5th_circuit",
        "manifest_prefix": "fifth_circuit",
    },
    "us-6th-circuit": {
        "vault_name": "6th Circuit",
        "display_name": "6th Circuit",
        "court_code": "US6C",
        "court_tag": "sixth-circuit",
        "source_id": "findlaw_us_6th_circuit",
        "manifest_prefix": "sixth_circuit",
    },
    "us-7th-circuit": {
        "vault_name": "7th Circuit",
        "display_name": "7th Circuit",
        "court_code": "US7C",
        "court_tag": "seventh-circuit",
        "source_id": "findlaw_us_7th_circuit",
        "manifest_prefix": "seventh_circuit",
    },
    "us-8th-circuit": {
        "vault_name": "8th Circuit",
        "display_name": "8th Circuit",
        "court_code": "US8C",
        "court_tag": "eighth-circuit",
        "source_id": "findlaw_us_8th_circuit",
        "manifest_prefix": "eighth_circuit",
    },
    "us-9th-circuit": {
        "vault_name": "9th Circuit",
        "display_name": "9th Circuit",
        "court_code": "US9C",
        "court_tag": "ninth-circuit",
        "source_id": "findlaw_us_9th_circuit",
        "manifest_prefix": "ninth_circuit",
    },
    "us-10th-circuit": {
        "vault_name": "10th Circuit",
        "display_name": "10th Circuit",
        "court_code": "US10C",
        "court_tag": "tenth-circuit",
        "source_id": "findlaw_us_10th_circuit",
        "manifest_prefix": "tenth_circuit",
    },
    "us-11th-circuit": {
        "vault_name": "11th Circuit",
        "display_name": "11th Circuit",
        "court_code": "US11C",
        "court_tag": "eleventh-circuit",
        "source_id": "findlaw_us_11th_circuit",
        "manifest_prefix": "eleventh_circuit",
    },
}


def _fallback_profile(court_slug: str) -> dict[str, str]:
    match = re.fullmatch(r"us-([0-9]{1,2}(?:st|nd|rd|th))-circuit", court_slug)
    label = match.group(1) if match else court_slug
    display = f"{label} Circuit"
    token = re.sub(r"[^a-z0-9]+", "_", display.lower()).strip("_")
    code = "US" + re.sub(r"[^0-9A-Za-z]+", "", label).upper()
    if not code.startswith("US"):
        code = f"US{code}"
    return {
        "vault_name": display,
        "display_name": display,
        "court_code": code,
        "court_tag": token.replace("_", "-"),
        "source_id": f"findlaw_{token}",
        "manifest_prefix": token,
    }


def resolve_circuit_profile(court_slug: str) -> dict[str, str]:
    return dict(CIRCUIT_PROFILES.get(court_slug, _fallback_profile(court_slug)))


ACTIVE_COURT_SLUG = "us-6th-circuit"
ACTIVE_COURT_ROOT = f"https://caselaw.findlaw.com/court/{ACTIVE_COURT_SLUG}"
ACTIVE_COURT_DISPLAY_NAME = "6th Circuit"
ACTIVE_COURT_CODE = "US6C"
ACTIVE_COURT_TAG = "sixth-circuit"
ACTIVE_SOURCE_ID = "findlaw_us_6th_circuit"
ACTIVE_MANIFEST_PREFIX = "sixth_circuit"
ACTIVE_VAULT_NAME = "6th Circuit"
ACTIVE_SCRIPT_DISPLAY_NAME = "scripts/ingest_6th_circuit_findlaw_obsidian.py"

CASE_LINK_RE = re.compile(
    r'^\[(?P<title>[^\]]+)\]\((?P<url>https?://caselaw\.findlaw\.com/court/us-6th-circuit/\d+\.html)(?:\s+"[^"]*")?\)$'
)
DATE_LINE_RE = re.compile(r"^[A-Za-z]+\s+\d{1,2},\s+\d{4}$")
PAGE_TOTAL_RE = re.compile(r"Page\s+\*\*\d+\*\*\s+of\s+\*\*(\d+)\*\*", re.IGNORECASE)
NEXT_LINK_RE = re.compile(
    r"\[Next\]\((https?://caselaw\.findlaw\.com/court/us-6th-circuit/[^)]+)\)",
    re.IGNORECASE,
)
CASE_ID_RE = re.compile(r"/([0-9]+)\.html$")
LINKED_FILE_RE = re.compile(r"\[[^\]]*here[^\]]*\]\((https?://[^)]+)\)", re.IGNORECASE)
PDF_URL_RE = re.compile(r"https?://[^\s)]+\.pdf", re.IGNORECASE)


def configure_circuit(
    *,
    court_slug: str,
    court_display_name: str,
    court_code: str,
    court_tag: str,
    source_id: str,
    manifest_prefix: str,
    vault_name: str,
) -> None:
    global ACTIVE_COURT_SLUG
    global ACTIVE_COURT_ROOT
    global ACTIVE_COURT_DISPLAY_NAME
    global ACTIVE_COURT_CODE
    global ACTIVE_COURT_TAG
    global ACTIVE_SOURCE_ID
    global ACTIVE_MANIFEST_PREFIX
    global ACTIVE_VAULT_NAME
    global CASE_LINK_RE
    global NEXT_LINK_RE

    ACTIVE_COURT_SLUG = court_slug
    ACTIVE_COURT_ROOT = f"https://caselaw.findlaw.com/court/{court_slug}"
    ACTIVE_COURT_DISPLAY_NAME = court_display_name
    ACTIVE_COURT_CODE = court_code
    ACTIVE_COURT_TAG = court_tag
    ACTIVE_SOURCE_ID = source_id
    ACTIVE_MANIFEST_PREFIX = manifest_prefix
    ACTIVE_VAULT_NAME = vault_name

    escaped_slug = re.escape(court_slug)
    CASE_LINK_RE = re.compile(
        rf'^\[(?P<title>[^\]]+)\]\((?P<url>https?://caselaw\.findlaw\.com/court/{escaped_slug}/\d+\.html)(?:\s+"[^"]*")?\)$'
    )
    NEXT_LINK_RE = re.compile(
        rf"\[Next\]\((https?://caselaw\.findlaw\.com/court/{escaped_slug}/[^)]+)\)",
        re.IGNORECASE,
    )


@dataclass(frozen=True)
class CaseListing:
    caption: str
    case_url: str
    decision_date: str
    case_number: str
    year_hint: int


@dataclass
class IngestRecord:
    case_id: str
    case_number: str
    caption: str
    decision_date: str
    findlaw_url: str
    source_url: str
    source_rel_path: str
    linked_file_url: str
    linked_file_rel_path: str
    md_rel_path: str
    linked_file_found: bool
    text_source: str
    error: str | None = None


def ingest_record_from_dict(data: dict) -> IngestRecord:
    return IngestRecord(
        case_id=str(data.get("case_id", "")),
        case_number=str(data.get("case_number", "")),
        caption=str(data.get("caption", "")),
        decision_date=str(data.get("decision_date", "")),
        findlaw_url=str(data.get("findlaw_url", "")),
        source_url=str(data.get("source_url", "")),
        source_rel_path=str(data.get("source_rel_path", data.get("source_path", ""))),
        linked_file_url=str(data.get("linked_file_url", "")),
        linked_file_rel_path=str(data.get("linked_file_rel_path", data.get("linked_file_path", ""))),
        md_rel_path=str(data.get("md_rel_path", data.get("md_path", ""))),
        linked_file_found=bool(data.get("linked_file_found", False)),
        text_source=str(data.get("text_source", "unknown")),
        error=data.get("error"),
    )


class RateLimiter:
    """Simple request pacing limiter with optional jitter."""

    def __init__(self, min_interval_seconds: float, jitter_seconds: float) -> None:
        self.min_interval_seconds = max(0.0, min_interval_seconds)
        self.jitter_seconds = max(0.0, jitter_seconds)
        self._last_request_monotonic = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        jitter = random.uniform(0.0, self.jitter_seconds) if self.jitter_seconds > 0 else 0.0
        target = self._last_request_monotonic + self.min_interval_seconds + jitter
        if now < target:
            time.sleep(target - now)
        self._last_request_monotonic = time.monotonic()


def build_session() -> requests.Session:
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "HEAD"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=8, pool_maxsize=8)
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": f"Acquittify-{ACTIVE_COURT_CODE}-Ingest/1.0",
            "Accept": "text/plain, text/markdown;q=0.9, */*;q=0.8",
        }
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def safe_yaml_text(raw: str) -> str:
    return raw.replace("\\", "\\\\").replace('"', '\\"')


def normalize_findlaw_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url.strip())
    if not parsed.scheme:
        parsed = urllib.parse.urlparse(f"https://{url.strip().lstrip('/')}" )
    scheme = "https"
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    query = parsed.query
    return urllib.parse.urlunparse((scheme, netloc, path, "", query, ""))


def to_jina_url(url: str) -> str:
    normalized = normalize_findlaw_url(url)
    if normalized.startswith("https://"):
        suffix = normalized[len("https://") :]
    elif normalized.startswith("http://"):
        suffix = normalized[len("http://") :]
    else:
        suffix = normalized
    return f"{JINA_HTTP_PREFIX}{suffix}"


def fetch_text(
    session: requests.Session,
    limiter: RateLimiter,
    url: str,
    timeout_seconds: int,
) -> str:
    limiter.wait()
    response = session.get(url, timeout=timeout_seconds)
    if response.status_code >= 400:
        raise RuntimeError(f"GET {url} -> HTTP {response.status_code}")
    return response.text


def snippet_for_error(text: str, max_chars: int = 220) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3] + "..."


def extract_markdown_content(jina_payload: str) -> str:
    marker = "Markdown Content:"
    idx = jina_payload.find(marker)
    if idx < 0:
        return jina_payload.strip()
    return jina_payload[idx + len(marker) :].lstrip("\n")


def fetch_markdown_with_retries(
    *,
    session: requests.Session,
    limiter: RateLimiter,
    page_url: str,
    timeout_seconds: int,
    fetch_max_attempts: int,
    fetch_retry_backoff_seconds: float,
    expected_page_check: Callable[[str], bool],
    page_label: str,
) -> str:
    attempts = max(1, fetch_max_attempts)
    last_reason = "unknown error"
    last_preview = ""

    for attempt in range(1, attempts + 1):
        try:
            payload = fetch_text(session, limiter, to_jina_url(page_url), timeout_seconds)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            last_reason = f"request error: {type(exc).__name__}: {exc}"
            if attempt < attempts:
                sleep_for_retry(attempt, fetch_retry_backoff_seconds)
            continue

        markdown_content = extract_markdown_content(payload)
        if expected_page_check(markdown_content):
            return markdown_content

        if is_verification_or_block_page(markdown_content):
            last_reason = "verification/challenge payload"
        else:
            last_reason = "unexpected payload shape"
        last_preview = snippet_for_error(markdown_content)
        if attempt < attempts:
            sleep_for_retry(attempt, fetch_retry_backoff_seconds)

    details = f"{page_label}: failed after {attempts} attempts ({last_reason})"
    if last_preview:
        details += f"; preview={last_preview}"
    raise RuntimeError(details)


def parse_decision_date(date_text: str) -> dt.date | None:
    try:
        return dt.datetime.strptime(date_text.strip(), "%B %d, %Y").date()
    except ValueError:
        return None


def compute_case_paths(vault_path: Path, listing: CaseListing) -> tuple[str, str, Path, Path, Path]:
    case_id = build_case_id(listing.case_url)
    decision_date_obj = parse_decision_date(listing.decision_date)
    decision_year = decision_date_obj.year if decision_date_obj is not None else listing.year_hint
    decision_date_iso = decision_date_obj.isoformat() if decision_date_obj is not None else ""

    slug_caption = sanitize_slug(listing.caption)[:80]
    case_slug = sanitize_slug(f"{case_id}-{slug_caption}")

    case_dir = vault_path / "Cases" / str(decision_year) / case_slug
    source_path = case_dir / f"{case_slug}.findlaw.md"
    note_path = case_dir / f"{case_slug}.md"
    return case_id, decision_date_iso, case_dir, source_path, note_path


def sleep_for_retry(attempt: int, base_seconds: float, max_seconds: float = 60.0) -> None:
    delay = min(max_seconds, max(0.1, base_seconds) * (2 ** min(attempt - 1, 6)))
    delay += random.uniform(0.0, 0.5)
    time.sleep(delay)


def sanitize_slug(raw: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", raw)
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-._")
    return cleaned or "case"


def build_case_id(case_url: str) -> str:
    match = CASE_ID_RE.search(case_url)
    if match:
        return match.group(1)
    token = hashlib.sha1(case_url.encode("utf-8")).hexdigest()[:12]
    return token


def looks_like_year_page(markdown_content: str, year: int) -> bool:
    if f"Browse by {year} Year Decisions" in markdown_content:
        return True
    if f"Court Decisions - {year}" in markdown_content:
        return True
    if f"/{year}" in markdown_content and "Year Decisions" in markdown_content:
        return True
    return False


def is_verification_or_block_page(markdown_content: str) -> bool:
    lowered = markdown_content.lower()
    markers = (
        "target url returned error 403",
        "security verification",
        "just a moment",
        "enable javascript and cookies to continue",
        "performing security verification",
    )
    return any(marker in lowered for marker in markers)


def looks_like_case_page(markdown_content: str) -> bool:
    content = markdown_content.strip()
    if not content:
        return False
    if is_verification_or_block_page(content):
        return False

    # Listing pages can occasionally be returned for case URLs; reject them.
    listing_case_links = re.findall(
        rf"https?://caselaw\.findlaw\.com/court/{re.escape(ACTIVE_COURT_SLUG)}/\d+\.html",
        content,
    )
    if len(listing_case_links) >= 8 and ("Court Decisions -" in content or "[Next](" in content):
        return False

    if "United States" in content and "Circuit" in content:
        return True
    if "FindLaw is currently processing this opinion." in content:
        return True
    if "### Decided:" in content:
        return True

    head = content[:300].upper()
    starts_with_markers = (
        "OPINION",
        "ORDER",
        "JUDGMENT",
        "PER CURIAM",
        "RECOMMENDED FOR FULL-TEXT PUBLICATION",
        "NOT RECOMMENDED FOR PUBLICATION",
    )
    if head.startswith(starts_with_markers):
        return True

    # Newer pages often begin directly with an opinion body.
    if len(content) >= 600 and "Court Decisions -" not in content:
        return True
    return False


def parse_total_pages(markdown_content: str) -> int:
    match = PAGE_TOTAL_RE.search(markdown_content)
    if not match:
        return 1
    try:
        return max(1, int(match.group(1)))
    except ValueError:
        return 1


def parse_next_page_url(markdown_content: str) -> str | None:
    match = NEXT_LINK_RE.search(markdown_content)
    if not match:
        return None
    return normalize_findlaw_url(match.group(1))


def parse_case_listings(markdown_content: str, year_hint: int) -> list[CaseListing]:
    lines = [line.rstrip() for line in markdown_content.splitlines()]
    listings: list[CaseListing] = []
    i = 0
    while i < len(lines):
        current = lines[i].strip()
        match = CASE_LINK_RE.match(current)
        if not match:
            i += 1
            continue

        caption = match.group("title").strip()
        case_url = normalize_findlaw_url(match.group("url"))

        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j >= len(lines):
            break
        decision_date = lines[j].strip()
        case_number = ""

        if DATE_LINE_RE.match(decision_date):
            j += 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            case_number = lines[j].strip() if j < len(lines) else ""
        else:
            # Rare malformed rows may omit/alter the date field; preserve the case URL anyway.
            case_number = decision_date
            decision_date = ""

        listings.append(
            CaseListing(
                caption=caption,
                case_url=case_url,
                decision_date=decision_date,
                case_number=case_number,
                year_hint=year_hint,
            )
        )
        i = j + 1

    deduped: list[CaseListing] = []
    seen_urls: set[str] = set()
    for listing in listings:
        if listing.case_url in seen_urls:
            continue
        seen_urls.add(listing.case_url)
        deduped.append(listing)
    return deduped


def collect_cases_for_year(
    session: requests.Session,
    limiter: RateLimiter,
    year: int,
    timeout_seconds: int,
    fetch_max_attempts: int,
    fetch_retry_backoff_seconds: float,
) -> list[CaseListing]:
    year_url = normalize_findlaw_url(f"{ACTIVE_COURT_ROOT}/{year}")
    next_url: str | None = year_url
    seen_pages: set[str] = set()
    all_listings: list[CaseListing] = []

    while next_url and next_url not in seen_pages:
        seen_pages.add(next_url)
        markdown_content = fetch_markdown_with_retries(
            session=session,
            limiter=limiter,
            page_url=next_url,
            timeout_seconds=timeout_seconds,
            fetch_max_attempts=fetch_max_attempts,
            fetch_retry_backoff_seconds=fetch_retry_backoff_seconds,
            expected_page_check=lambda content: looks_like_year_page(content, year),
            page_label=f"year listing {year} ({next_url})",
        )

        page_listings = parse_case_listings(markdown_content, year_hint=year)
        all_listings.extend(page_listings)

        next_url = parse_next_page_url(markdown_content)

    deduped: list[CaseListing] = []
    seen_urls: set[str] = set()
    for listing in all_listings:
        if listing.case_url in seen_urls:
            continue
        seen_urls.add(listing.case_url)
        deduped.append(listing)
    return deduped


def extract_case_body(markdown_content: str) -> str:
    lines = [line.rstrip() for line in markdown_content.splitlines()]

    # Old case pages often include long site navigation before the case block.
    if any("Skip to main content" in line for line in lines):
        start_idx = 0
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if stripped == "OPINION":
                start_idx = idx
                break
            if "United States" in stripped and "Circuit" in stripped:
                start_idx = idx
                break
        lines = lines[start_idx:]

    end_markers = (
        "Was this helpful?",
        "### Get updates from FindLaw Legal Professionals",
        "Back to Top",
        "Find a Lawyer",
        "Search by Legal Topic",
    )
    end_idx = len(lines)
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if any(stripped.startswith(marker) for marker in end_markers):
            end_idx = idx
            break

    cleaned = "\n".join(lines[:end_idx]).strip()
    return cleaned or markdown_content.strip()


def extract_linked_file_url(markdown_content: str) -> str:
    match = LINKED_FILE_RE.search(markdown_content)
    if match:
        return match.group(1).strip()
    match = PDF_URL_RE.search(markdown_content)
    if match:
        return match.group(0).strip()
    return ""


def guess_linked_file_extension(file_url: str) -> str:
    parsed = urllib.parse.urlparse(file_url)
    suffix = Path(parsed.path).suffix.lower()
    if suffix in {".pdf", ".txt", ".html", ".htm", ".doc", ".docx"}:
        return suffix
    return ".bin"


def download_linked_file(
    session: requests.Session,
    limiter: RateLimiter,
    file_url: str,
    output_path: Path,
    timeout_seconds: int,
    max_bytes: int,
) -> tuple[bool, str | None]:
    limiter.wait()
    try:
        with session.get(file_url, timeout=timeout_seconds, stream=True, allow_redirects=True) as response:
            if response.status_code >= 400:
                return False, f"HTTP {response.status_code}"

            content_length_raw = response.headers.get("Content-Length", "").strip()
            if max_bytes > 0 and content_length_raw.isdigit() and int(content_length_raw) > max_bytes:
                return False, f"content-length exceeds max-bytes ({content_length_raw}>{max_bytes})"

            output_path.parent.mkdir(parents=True, exist_ok=True)
            total_written = 0
            with output_path.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    total_written += len(chunk)
                    if max_bytes > 0 and total_written > max_bytes:
                        handle.close()
                        output_path.unlink(missing_ok=True)
                        return False, f"download exceeds max-bytes ({total_written}>{max_bytes})"
                    handle.write(chunk)
    except requests.RequestException as exc:
        return False, str(exc)

    return True, None


def write_case_note(
    md_path: Path,
    *,
    case_id: str,
    listing: CaseListing,
    decision_date_iso: str,
    findlaw_url: str,
    source_rel: Path,
    linked_file_url: str,
    linked_file_rel: Path | None,
    linked_file_found: bool,
    text_source: str,
    extracted_text: str,
) -> None:
    frontmatter_lines = [
        "---",
        f'case_id: "{safe_yaml_text(ACTIVE_COURT_CODE)}-{safe_yaml_text(case_id)}"',
        f'case_number: "{safe_yaml_text(listing.case_number)}"',
        f'caption: "{safe_yaml_text(listing.caption)}"',
        f'decision_date: "{safe_yaml_text(decision_date_iso)}"',
        f'source: "{safe_yaml_text(ACTIVE_SOURCE_ID)}"',
        f'findlaw_url: "{safe_yaml_text(findlaw_url)}"',
        f'source_file: "{safe_yaml_text(source_rel.as_posix())}"',
        f'linked_file_url: "{safe_yaml_text(linked_file_url)}"',
        f'linked_file: "{safe_yaml_text(linked_file_rel.as_posix() if linked_file_rel else "")}"',
        f'extracted_text_source: "{safe_yaml_text(text_source)}"',
        "tags:",
        f"  - {safe_yaml_text(ACTIVE_COURT_TAG)}",
        "  - case",
        "---",
        "",
    ]

    linked_file_line = "- Linked File: `missing`"
    if linked_file_rel is not None and linked_file_found:
        linked_file_line = f"- Linked File: `[[{linked_file_rel.name}]]`"
    elif linked_file_url:
        linked_file_line = f"- Linked File URL: `{linked_file_url}`"

    body_lines = [
        f"# {listing.caption}",
        "",
        f"- Case Number: `{listing.case_number}`" if listing.case_number else "- Case Number: `unknown`",
        f"- Decision Date: `{decision_date_iso}`" if decision_date_iso else "- Decision Date: `unknown`",
        f"- FindLaw URL: `{findlaw_url}`",
        f"- Source Page: `[[{source_rel.name}]]`",
        linked_file_line,
        "",
        "## Extracted Text",
        "",
        extracted_text.strip() if extracted_text.strip() else "_No extracted text available._",
        "",
    ]

    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(frontmatter_lines + body_lines), encoding="utf-8")


def process_case(
    listing: CaseListing,
    *,
    vault_path: Path,
    session: requests.Session,
    limiter: RateLimiter,
    timeout_seconds: int,
    fetch_max_attempts: int,
    fetch_retry_backoff_seconds: float,
    refresh: bool,
    download_linked_files: bool,
    linked_file_max_bytes: int,
) -> IngestRecord:
    case_id, decision_date_iso, case_dir, source_path, note_path = compute_case_paths(vault_path, listing)
    case_slug = note_path.stem
    case_dir.mkdir(parents=True, exist_ok=True)

    source_url = to_jina_url(listing.case_url)
    if refresh or not source_path.exists():
        source_markdown = fetch_markdown_with_retries(
            session=session,
            limiter=limiter,
            page_url=listing.case_url,
            timeout_seconds=timeout_seconds,
            fetch_max_attempts=fetch_max_attempts,
            fetch_retry_backoff_seconds=fetch_retry_backoff_seconds,
            expected_page_check=looks_like_case_page,
            page_label=f"case page {listing.case_url}",
        )
        source_path.write_text(source_markdown, encoding="utf-8")
    else:
        source_markdown = source_path.read_text(encoding="utf-8", errors="ignore")

    extracted_text = extract_case_body(source_markdown)
    linked_file_url = extract_linked_file_url(source_markdown)
    linked_file_path: Path | None = None
    linked_file_found = False
    linked_file_error: str | None = None

    if linked_file_url and download_linked_files:
        extension = guess_linked_file_extension(linked_file_url)
        linked_file_path = case_dir / f"{case_slug}{extension}"
        if refresh or not linked_file_path.exists():
            linked_file_found, linked_file_error = download_linked_file(
                session,
                limiter,
                linked_file_url,
                linked_file_path,
                timeout_seconds,
                linked_file_max_bytes,
            )
        else:
            linked_file_found = True

    source_rel = source_path.relative_to(vault_path)
    linked_file_rel = linked_file_path.relative_to(vault_path) if linked_file_path and linked_file_found else None
    note_rel = note_path.relative_to(vault_path)

    text_source = "findlaw_case_page"
    if linked_file_url and download_linked_files and not linked_file_found and linked_file_error:
        text_source = f"findlaw_case_page (linked_file_error={linked_file_error})"

    write_case_note(
        note_path,
        case_id=case_id,
        listing=listing,
        decision_date_iso=decision_date_iso,
        findlaw_url=listing.case_url,
        source_rel=source_rel,
        linked_file_url=linked_file_url,
        linked_file_rel=linked_file_rel,
        linked_file_found=linked_file_found,
        text_source=text_source,
        extracted_text=extracted_text,
    )

    return IngestRecord(
        case_id=f"{ACTIVE_COURT_CODE}-{case_id}",
        case_number=listing.case_number,
        caption=listing.caption,
        decision_date=decision_date_iso,
        findlaw_url=listing.case_url,
        source_url=source_url,
        source_rel_path=source_rel.as_posix(),
        linked_file_url=linked_file_url,
        linked_file_rel_path=linked_file_rel.as_posix() if linked_file_rel else "",
        md_rel_path=note_rel.as_posix(),
        linked_file_found=linked_file_found,
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
        if record.linked_file_found and not existing.linked_file_found:
            unique_by_note_path[key] = record

    records_sorted = sorted(
        unique_by_note_path.values(),
        key=lambda item: (item.decision_date or "0000-00-00", item.case_id),
    )

    csv_path = ontology_dir / f"{ACTIVE_MANIFEST_PREFIX}_case_file_links.csv"
    jsonl_path = ontology_dir / f"{ACTIVE_MANIFEST_PREFIX}_case_file_links.jsonl"

    headers = [
        "case_id",
        "case_number",
        "caption",
        "decision_date",
        "findlaw_url",
        "source_url",
        "source_path",
        "linked_file_url",
        "linked_file_path",
        "md_path",
        "linked_file_found",
        "text_source",
        "error",
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
                    "findlaw_url": record.findlaw_url,
                    "source_url": record.source_url,
                    "source_path": record.source_rel_path,
                    "linked_file_url": record.linked_file_url,
                    "linked_file_path": record.linked_file_rel_path,
                    "md_path": record.md_rel_path,
                    "linked_file_found": record.linked_file_found,
                    "text_source": record.text_source,
                    "error": record.error or "",
                }
            )

    with jsonl_path.open("w", encoding="utf-8") as jsonl_file:
        for record in records_sorted:
            jsonl_file.write(json.dumps(record.__dict__, ensure_ascii=False) + "\n")

    total = len(records_sorted)
    with_linked_file = sum(1 for record in records_sorted if record.linked_file_found)
    without_linked_file = total - with_linked_file
    return {
        "total": total,
        "with_linked_file": with_linked_file,
        "missing_linked_file": without_linked_file,
    }


def load_existing_manifest_records(vault_path: Path) -> list[IngestRecord]:
    manifest_path = vault_path / "Ontology" / f"{ACTIVE_MANIFEST_PREFIX}_case_file_links.jsonl"
    if not manifest_path.exists():
        return []

    records: list[IngestRecord] = []
    for line in manifest_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        record = ingest_record_from_dict(payload)
        if record.findlaw_url:
            records.append(record)
    return records


def record_from_local_files(vault_path: Path, listing: CaseListing) -> IngestRecord | None:
    case_id, decision_date_iso, _case_dir, source_path, note_path = compute_case_paths(vault_path, listing)
    if not note_path.exists():
        return None

    source_rel_path = source_path.relative_to(vault_path).as_posix() if source_path.exists() else ""
    note_rel_path = note_path.relative_to(vault_path).as_posix()

    linked_file_url = ""
    linked_file_rel_path = ""
    linked_file_found = False
    text_source = "findlaw_case_page"

    note_text = note_path.read_text(encoding="utf-8", errors="ignore")
    linked_url_match = re.search(r'^linked_file_url:\s*"([^"]*)"', note_text, flags=re.MULTILINE)
    if linked_url_match:
        linked_file_url = linked_url_match.group(1).strip()

    linked_path_match = re.search(r'^linked_file:\s*"([^"]*)"', note_text, flags=re.MULTILINE)
    if linked_path_match:
        candidate = linked_path_match.group(1).strip()
        if candidate:
            linked_file_rel_path = candidate
            linked_file_found = (vault_path / candidate).exists()

    text_source_match = re.search(r'^extracted_text_source:\s*"([^"]*)"', note_text, flags=re.MULTILINE)
    if text_source_match:
        extracted_text_source = text_source_match.group(1).strip()
        if extracted_text_source:
            text_source = extracted_text_source

    return IngestRecord(
        case_id=f"{ACTIVE_COURT_CODE}-{case_id}",
        case_number=listing.case_number,
        caption=listing.caption,
        decision_date=decision_date_iso,
        findlaw_url=listing.case_url,
        source_url=to_jina_url(listing.case_url),
        source_rel_path=source_rel_path,
        linked_file_url=linked_file_url,
        linked_file_rel_path=linked_file_rel_path,
        md_rel_path=note_rel_path,
        linked_file_found=linked_file_found,
        text_source=text_source,
    )


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
    run_id = f"{ACTIVE_MANIFEST_PREFIX}-findlaw-ingest-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

    deduped_records: list[IngestRecord] = []
    seen_note_paths: set[str] = set()
    for record in records:
        if record.md_rel_path in seen_note_paths:
            continue
        seen_note_paths.add(record.md_rel_path)
        deduped_records.append(record)

    for record in deduped_records:
        stable_token = hashlib.sha1(record.md_rel_path.encode("utf-8")).hexdigest()[:12]
        case_object_id = f"case::{record.case_id}::{stable_token}"
        case_meta = {
            "case_number": record.case_number,
            "caption": record.caption,
            "decision_date": record.decision_date,
            "findlaw_url": record.findlaw_url,
            "source_url": record.source_url,
            "source_path": record.source_rel_path,
            "linked_file_url": record.linked_file_url,
            "linked_file_path": record.linked_file_rel_path,
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
                json.dumps(["AQ.CASE", ACTIVE_COURT_CODE], ensure_ascii=False),
                json.dumps(case_meta, ensure_ascii=False),
                now_iso,
                now_iso,
            ),
        )

        if record.linked_file_found and record.linked_file_rel_path:
            doc_object_id = f"doc::{record.case_id}::{stable_token}::linked"
            doc_meta = {
                "case_id": record.case_id,
                "source": "findlaw_linked_file",
                "linked_file_url": record.linked_file_url,
                "file_path": record.linked_file_rel_path,
            }
            cur.execute(
                """
                INSERT INTO ontology_objects (
                    object_id, object_type, name, note_path, taxonomy_codes, metadata, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_object_id,
                    "AQ.DOCUMENT",
                    f"{record.caption} (Linked File)",
                    record.linked_file_rel_path,
                    json.dumps(["AQ.DOCUMENT", ACTIVE_COURT_CODE], ensure_ascii=False),
                    json.dumps(doc_meta, ensure_ascii=False),
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
                    doc_object_id,
                    record.md_rel_path,
                    f"linked_file={record.linked_file_rel_path}",
                    now_iso,
                ),
            )

    payload = {
        "records": len(deduped_records),
        "linked_file_records": sum(1 for r in deduped_records if r.linked_file_found),
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
            ACTIVE_SOURCE_ID,
            ".ponner/federation.sqlite3",
            json.dumps(payload, ensure_ascii=False),
            now_iso,
        ),
    )

    conn.commit()
    conn.close()
    return db_path


def write_summary(
    vault_path: Path,
    summary: dict[str, int],
    *,
    elapsed_seconds: float,
    since_year: int,
    until_year: int,
    request_interval_seconds: float,
    request_jitter_seconds: float,
    fetch_max_attempts: int,
    fetch_retry_backoff_seconds: float,
    download_linked_files: bool,
) -> Path:
    summary_path = vault_path / "Ontology" / "ingest_summary.json"
    payload = {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "elapsed_seconds": round(elapsed_seconds, 3),
        "source": ACTIVE_SOURCE_ID,
        "since_year": since_year,
        "until_year": until_year,
        "total_cases_ingested": summary["total"],
        "cases_with_linked_file_downloaded": summary["with_linked_file"],
        "cases_without_linked_file_downloaded": summary["missing_linked_file"],
        "request_interval_seconds": request_interval_seconds,
        "request_jitter_seconds": request_jitter_seconds,
        "fetch_max_attempts": fetch_max_attempts,
        "fetch_retry_backoff_seconds": fetch_retry_backoff_seconds,
        "download_linked_files": download_linked_files,
        "vault_path": str(vault_path),
    }
    summary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return summary_path


def ensure_vault_readme(vault_path: Path) -> None:
    readme_path = vault_path / "README.md"
    if readme_path.exists():
        return

    script_path = ACTIVE_SCRIPT_DISPLAY_NAME
    title = f"{ACTIVE_VAULT_NAME} Vault"
    content = f"""# {title}

This vault was generated by `{script_path}`.

## Structure

- `Cases/<year>/<case_slug>/<case_slug>.findlaw.md` - source markdown fetched from FindLaw
- `Cases/<year>/<case_slug>/<case_slug>.md` - normalized case note
- `Cases/<year>/<case_slug>/<case_slug>.<ext>` - linked native file when downloaded (optional)
- `Ontology/{ACTIVE_MANIFEST_PREFIX}_case_file_links.csv` - case/file linkage manifest
- `Ontology/{ACTIVE_MANIFEST_PREFIX}_case_file_links.jsonl` - machine-readable manifest
- `.ponner/federation.sqlite3` - ontology objects + links for Acquittify

## Resume ingestion

From the repository root:

```bash
python3 -u {script_path} \\
  --vault-path "$ACQUITTIFY_OBSIDIAN_ROOT/{ACTIVE_VAULT_NAME}" \\
  --since-year 2010 \\
  --request-interval-seconds 2.5 \\
  --request-jitter-seconds 0.5
```

The script reuses existing manifest entries and only processes missing records unless `--refresh` is provided.
"""
    readme_path.write_text(content, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Ingest US federal circuit cases from FindLaw into a co-located Obsidian vault "
            "with conservative throttling defaults."
        )
    )
    parser.add_argument(
        "--court-slug",
        default=os.getenv("ACQ_FINDLAW_COURT_SLUG", "us-6th-circuit"),
        help='FindLaw circuit slug under /court/ (example: "us-dc-circuit").',
    )
    parser.add_argument(
        "--court-vault-name",
        default="",
        help='Vault folder name under Obsidian Documents (default: derived from --court-slug).',
    )
    parser.add_argument(
        "--court-display-name",
        default="",
        help='Human label used in logs/README (default: derived from --court-slug).',
    )
    parser.add_argument(
        "--court-code",
        default="",
        help='Short court code for case IDs/ontology taxonomy (default: derived from --court-slug).',
    )
    parser.add_argument(
        "--court-tag",
        default="",
        help='Tag added to case notes (default: derived from --court-slug).',
    )
    parser.add_argument(
        "--source-id",
        default="",
        help='Source identifier used in note frontmatter and summary (default: derived from --court-slug).',
    )
    parser.add_argument(
        "--manifest-prefix",
        default="",
        help='Prefix for manifest filenames (default: derived from --court-slug).',
    )
    parser.add_argument(
        "--vault-path",
        default="",
        help="Vault directory path (default: Obsidian Documents/<court-vault-name>).",
    )
    parser.add_argument(
        "--since-year",
        type=int,
        default=2010,
        help="Only ingest cases with decision date on/after Jan 1 of this year.",
    )
    parser.add_argument(
        "--until-year",
        type=int,
        default=dt.date.today().year,
        help="Only ingest cases with decision date on/before Dec 31 of this year.",
    )
    parser.add_argument(
        "--request-interval-seconds",
        type=float,
        default=2.5,
        help="Minimum delay between network requests (default: 2.5).",
    )
    parser.add_argument(
        "--request-jitter-seconds",
        type=float,
        default=0.5,
        help="Additional randomized delay (0..jitter) between requests (default: 0.5).",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Per-request timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS}).",
    )
    parser.add_argument(
        "--fetch-max-attempts",
        type=int,
        default=12,
        help="Maximum attempts per FindLaw page fetch before failing (default: 12).",
    )
    parser.add_argument(
        "--fetch-retry-backoff-seconds",
        type=float,
        default=1.0,
        help="Base exponential backoff (seconds) between fetch retries (default: 1.0).",
    )
    parser.add_argument(
        "--max-cases",
        type=int,
        default=0,
        help="Optional cap on total cases processed this run (0 = no limit).",
    )
    parser.add_argument(
        "--download-linked-files",
        action="store_true",
        help="Download linked native files (e.g., PDFs) when present in FindLaw pages.",
    )
    parser.add_argument(
        "--linked-file-max-bytes",
        type=int,
        default=25_000_000,
        help="Max bytes for each linked-file download (default: 25,000,000).",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-download and re-write existing case artifacts.",
    )
    args = parser.parse_args()
    args.court_slug = args.court_slug.strip().lower()
    profile = resolve_circuit_profile(args.court_slug)

    env_vault_name = os.getenv("ACQ_FINDLAW_VAULT_NAME", "").strip()
    env_display_name = os.getenv("ACQ_FINDLAW_COURT_DISPLAY_NAME", "").strip()
    env_court_code = os.getenv("ACQ_FINDLAW_COURT_CODE", "").strip()
    env_court_tag = os.getenv("ACQ_FINDLAW_TAG", "").strip()
    env_source_id = os.getenv("ACQ_FINDLAW_SOURCE_ID", "").strip()
    env_manifest_prefix = os.getenv("ACQ_FINDLAW_MANIFEST_PREFIX", "").strip()

    args.court_vault_name = args.court_vault_name.strip() or env_vault_name or profile["vault_name"]
    args.court_display_name = args.court_display_name.strip() or env_display_name or profile["display_name"]
    args.court_code = args.court_code.strip() or env_court_code or profile["court_code"]
    args.court_tag = args.court_tag.strip() or env_court_tag or profile["court_tag"]
    args.source_id = args.source_id.strip() or env_source_id or profile["source_id"]
    args.manifest_prefix = args.manifest_prefix.strip() or env_manifest_prefix or profile["manifest_prefix"]

    if args.vault_path.strip():
        args.vault_path = args.vault_path.strip()
    else:
        args.vault_path = str(OBSIDIAN_DOCUMENTS_ROOT / args.court_vault_name)

    return args


def main() -> int:
    args = parse_args()
    if args.since_year > args.until_year:
        raise SystemExit("--since-year must be <= --until-year")

    configure_circuit(
        court_slug=args.court_slug,
        court_display_name=args.court_display_name,
        court_code=args.court_code,
        court_tag=args.court_tag,
        source_id=args.source_id,
        manifest_prefix=args.manifest_prefix,
        vault_name=args.court_vault_name,
    )

    start_time = dt.datetime.now(dt.timezone.utc)
    vault_path = Path(args.vault_path).expanduser().resolve()
    vault_path.mkdir(parents=True, exist_ok=True)
    ensure_vault_readme(vault_path)

    session = build_session()
    limiter = RateLimiter(args.request_interval_seconds, args.request_jitter_seconds)

    print(f"Vault: {vault_path}")
    print(
        "Circuit:",
        f"slug={ACTIVE_COURT_SLUG}",
        f"code={ACTIVE_COURT_CODE}",
        f"source={ACTIVE_SOURCE_ID}",
    )
    print(
        "Throttle:",
        f"interval={args.request_interval_seconds}s",
        f"jitter={args.request_jitter_seconds}s",
        f"download_linked_files={args.download_linked_files}",
    )
    print(f"Discovering year pages from {args.since_year} to {args.until_year}...")

    all_listings: list[CaseListing] = []
    for year in range(args.until_year, args.since_year - 1, -1):
        try:
            listings = collect_cases_for_year(
                session=session,
                limiter=limiter,
                year=year,
                timeout_seconds=args.timeout_seconds,
                fetch_max_attempts=args.fetch_max_attempts,
                fetch_retry_backoff_seconds=args.fetch_retry_backoff_seconds,
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print(f"Year {year}: error collecting listings: {exc}")
            continue

        if not listings:
            print(f"Year {year}: no listings found")
            continue

        print(f"Year {year}: discovered {len(listings)} cases")
        all_listings.extend(listings)

    deduped_listings: list[CaseListing] = []
    seen_case_urls: set[str] = set()
    for listing in all_listings:
        if listing.case_url in seen_case_urls:
            continue
        seen_case_urls.add(listing.case_url)
        deduped_listings.append(listing)

    if args.max_cases > 0:
        deduped_listings = deduped_listings[: args.max_cases]
        print(f"Applying --max-cases cap: {len(deduped_listings)}")

    print(f"Total candidate cases: {len(deduped_listings)}")

    existing_by_findlaw_url: dict[str, IngestRecord] = {}
    if not args.refresh:
        for record in load_existing_manifest_records(vault_path):
            existing_by_findlaw_url[record.findlaw_url] = record
        if existing_by_findlaw_url:
            print(f"Loaded existing manifest records: {len(existing_by_findlaw_url)}")

    records: list[IngestRecord] = []
    errors: list[str] = []
    queue: list[CaseListing] = []
    reused_complete = 0
    reused_local_files = 0

    live_errors_path = vault_path / "Ontology" / "ingest_errors.live.log"
    live_errors_path.parent.mkdir(parents=True, exist_ok=True)
    live_errors_path.write_text("", encoding="utf-8")

    for listing in deduped_listings:
        existing = existing_by_findlaw_url.get(listing.case_url)
        if existing is None or args.refresh:
            local_record = None if args.refresh else record_from_local_files(vault_path, listing)
            if local_record is not None:
                records.append(local_record)
                reused_local_files += 1
            else:
                queue.append(listing)
            continue

        source_exists = bool(existing.source_rel_path) and (vault_path / existing.source_rel_path).exists()
        note_exists = bool(existing.md_rel_path) and (vault_path / existing.md_rel_path).exists()
        linked_exists = (not existing.linked_file_found) or (
            bool(existing.linked_file_rel_path) and (vault_path / existing.linked_file_rel_path).exists()
        )

        if source_exists and note_exists and linked_exists:
            records.append(existing)
            reused_complete += 1
            continue

        queue.append(listing)

    if reused_complete:
        print(f"Reused complete records: {reused_complete}")
    if reused_local_files:
        print(f"Reused records from existing local files: {reused_local_files}")

    total_to_process = len(queue)
    print(f"Queued for processing: {total_to_process}")

    for idx, listing in enumerate(queue, start=1):
        try:
            record = process_case(
                listing,
                vault_path=vault_path,
                session=session,
                limiter=limiter,
                timeout_seconds=args.timeout_seconds,
                fetch_max_attempts=args.fetch_max_attempts,
                fetch_retry_backoff_seconds=args.fetch_retry_backoff_seconds,
                refresh=args.refresh,
                download_linked_files=args.download_linked_files,
                linked_file_max_bytes=args.linked_file_max_bytes,
            )
            records.append(record)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            line = f"{listing.case_url}: {exc}"
            errors.append(line)
            with live_errors_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")

        if idx % 25 == 0 or idx == total_to_process:
            print(f"Progress: {idx}/{total_to_process} processed, records={len(records)}, errors={len(errors)}")

    summary = write_manifests(vault_path, records)
    db_path = build_ontology_db(vault_path, records)
    elapsed_seconds = (dt.datetime.now(dt.timezone.utc) - start_time).total_seconds()
    summary_path = write_summary(
        vault_path,
        summary,
        elapsed_seconds=elapsed_seconds,
        since_year=args.since_year,
        until_year=args.until_year,
        request_interval_seconds=args.request_interval_seconds,
        request_jitter_seconds=args.request_jitter_seconds,
        fetch_max_attempts=args.fetch_max_attempts,
        fetch_retry_backoff_seconds=args.fetch_retry_backoff_seconds,
        download_linked_files=args.download_linked_files,
    )

    if errors:
        errors_path = vault_path / "Ontology" / "ingest_errors.log"
        errors_path.write_text("\n".join(errors), encoding="utf-8")
        print(f"Wrote errors: {errors_path} ({len(errors)})")
    else:
        live_errors_path.unlink(missing_ok=True)

    print(f"Ontology DB: {db_path}")
    print(f"Summary: {summary_path}")
    print(
        "Counts:",
        f"total={summary['total']}",
        f"with_linked_file={summary['with_linked_file']}",
        f"missing_linked_file={summary['missing_linked_file']}",
    )
    print(f"Elapsed seconds: {elapsed_seconds:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
