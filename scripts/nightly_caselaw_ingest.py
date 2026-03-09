#!/usr/bin/env python3
"""Nightly federal criminal caselaw ingest from CourtListener.

Workflow:
1) Pull today's SCOTUS decisions.
2) Pull today's Federal Circuit decisions.
3) Work backward across federal courts while runtime budget remains.
4) Deduplicate by CourtListener cluster id and upsert into Postgres.
5) Persist taxonomy codes and YAML frontmatter for fast retrieval.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row
import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acquittify.ontology.taxonomy_case_map import map_case_taxonomies

# --- Minimal text utilities (formerly ingestion_agent.*) ---

HTML_TAG_RE = re.compile(r"<[^>]+>")
HTML_ENTITY_REPLACEMENTS = {
    "&nbsp;": " ",
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
}
TABLE_OF_AUTHORITIES_RE = re.compile(r"\bTABLE OF AUTHORITIES\b", re.IGNORECASE)
PAGE_NUMBER_RE = re.compile(r"^\s*(?:-\s*)?\d+\s*(?:-\s*)?$")
HEADER_FOOTER_RE = re.compile(r"^\s*Page\s+\d+\s+of\s+\d+\s*$", re.IGNORECASE)
JUDGE_SIGNATURE_RE = re.compile(r"^\s*(/s/|s/)\s+.+$", re.IGNORECASE)
JUDGE_TITLE_RE = re.compile(
    r"^\s*(Chief\s+)?(United\s+States\s+)?(District|Circuit|Magistrate|Bankruptcy)\s+Judge\b",
    re.IGNORECASE,
)
SIGNED_BY_RE = re.compile(r"^\s*Signed\s+by\s+.+$", re.IGNORECASE)


def _normalize_line_endings(text: str) -> str:
    return str(text or "").replace("\r\n", "\n").replace("\r", "\n")


def strip_html(text: str) -> str:
    if not text:
        return ""
    cleaned = HTML_TAG_RE.sub(" ", text)
    for entity, replacement in HTML_ENTITY_REPLACEMENTS.items():
        cleaned = cleaned.replace(entity, replacement)
    return cleaned


def _remove_tables_of_authorities(text: str) -> str:
    if not TABLE_OF_AUTHORITIES_RE.search(text):
        return text
    lines = text.splitlines()
    cleaned = []
    skipping = False
    for line in lines:
        if TABLE_OF_AUTHORITIES_RE.search(line):
            skipping = True
            continue
        if skipping and not line.strip():
            skipping = False
            continue
        if not skipping:
            cleaned.append(line)
    return "\n".join(cleaned)


def _remove_headers_footers(text: str) -> str:
    lines = text.splitlines()
    cleaned = []
    for line in lines:
        if HEADER_FOOTER_RE.match(line):
            continue
        if PAGE_NUMBER_RE.match(line.strip()):
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def _remove_judge_signatures(text: str) -> str:
    lines = text.splitlines()
    end = len(lines) - 1
    while end >= 0:
        line = lines[end].strip()
        if not line:
            end -= 1
            continue
        if (
            JUDGE_SIGNATURE_RE.match(line)
            or JUDGE_TITLE_RE.match(line)
            or SIGNED_BY_RE.match(line)
        ):
            end -= 1
            continue
        break
    return "\n".join(lines[: end + 1])


def _normalize_whitespace(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_text(text: str) -> str:
    text = _normalize_line_endings(text)
    text = _remove_tables_of_authorities(text)
    text = _remove_headers_footers(text)
    text = _remove_judge_signatures(text)
    text = _normalize_whitespace(text)
    return text

DEFAULT_SEARCH_URL = "https://www.courtlistener.com/api/rest/v4/search/"
DEFAULT_COURTS_URL = "https://www.courtlistener.com/api/rest/v4/courts/"
DEFAULT_OPINIONS_URL = "https://www.courtlistener.com/api/rest/v4/opinions/"
DEFAULT_STATE_KEY = "courtlistener_federal_criminal_nightly"
DEFAULT_TIMEZONE = "America/Detroit"
DEFAULT_RUNTIME_HOURS = 6.0
PRIORITY_COURTS = ("scotus", "cafc")

CRIMINAL_PATTERNS = [
    re.compile(r"\b(18|21|26|49)\s*u\.?s\.?c\b", re.IGNORECASE),
    re.compile(r"\b(indict(?:ment|ed)?|convict(?:ion|ed)?|sentenc(?:e|ing)|plea(?:d|s|ing)?)\b", re.IGNORECASE),
    re.compile(r"\b(miranda|suppression|felony|misdemeanor|grand jury)\b", re.IGNORECASE),
    re.compile(r"\b(rule\s+11|rule\s+29|rule\s+33|924\(c\)|922\(g\))\b", re.IGNORECASE),
]

QUASI_CRIMINAL_PATTERNS = [
    re.compile(r"\b(2255|habeas|2241|post-conviction|postconviction)\b", re.IGNORECASE),
]

FALLBACK_TAXONOMY_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bmiranda\b", re.IGNORECASE), "5A.MIR.GEN.GEN"),
    (re.compile(r"\bineffective\s+assistance|strickland\b", re.IGNORECASE), "6A.IAC.GEN.GEN"),
    (re.compile(r"\bconfrontation|crawford\b", re.IGNORECASE), "6A.CONFR.GEN.GEN"),
    (re.compile(r"\bsearch|seizure|warrant|suppression\b", re.IGNORECASE), "4A.SUPP.GEN.GEN"),
    (re.compile(r"\bbrady|giglio|jencks|discovery\b", re.IGNORECASE), "DISC.BRADY.GEN.GEN"),
    (re.compile(r"\bdaubert|hearsay|evidence\b", re.IGNORECASE), "EVID.R403.GEN.GEN"),
    (re.compile(r"\bspeedy\s+trial\b", re.IGNORECASE), "6A.SPEEDY.GEN.GEN"),
    (re.compile(r"\bjury|batson|voir\s+dire\b", re.IGNORECASE), "6A.JURY.GEN.GEN"),
    (re.compile(r"\bsentenc|guideline|3553\b", re.IGNORECASE), "SENT.GUIDE.GEN.GEN"),
    (re.compile(r"\bforfeiture\b", re.IGNORECASE), "SENT.FORFEIT.NEXUS.GEN"),
    (re.compile(r"\bbail|detention\b", re.IGNORECASE), "PROC.BAIL.DETAIN.FACTORS"),
    (re.compile(r"\bindict|superseding\b", re.IGNORECASE), "PROC.INDICT.DEFECT.FAILSTATE"),
    (re.compile(r"\bvenue|jurisdiction\b", re.IGNORECASE), "PROC.VENUE.PROPER.DIST"),
    (re.compile(r"\bappeal|sufficiency\b", re.IGNORECASE), "APP.SUFF.GEN.GEN"),
]

DEFAULT_FALLBACK_CODE = "PROC.MOT.DISMISS.GENERAL"


@dataclass(frozen=True)
class Config:
    db_dsn: str
    courtlistener_token: str | None
    timezone_name: str
    max_runtime_seconds: int
    state_key: str
    taxonomy_path: Path
    aliases_path: Path | None
    log_path: Path
    include_quasi_criminal: bool
    only_courts: tuple[str, ...] | None
    backfill_start_date: date | None
    page_size: int
    max_pages_per_query: int
    request_timeout_seconds: int
    request_pause_seconds: float
    request_retries: int
    max_court_date_queries: int
    dry_run: bool


@dataclass(frozen=True)
class TaxonomyNodeEntry:
    code: str
    label: str
    parent_code: str | None
    synonyms: list[str]


class CourtListenerClient:
    """Client for CourtListener v4 search + courts + opinion detail endpoints."""

    def __init__(
        self,
        *,
        token: str | None,
        search_url: str = DEFAULT_SEARCH_URL,
        courts_url: str = DEFAULT_COURTS_URL,
        opinions_url: str = DEFAULT_OPINIONS_URL,
        timeout_seconds: int = 30,
        pause_seconds: float = 0.15,
        retries: int = 5,
    ) -> None:
        self.search_url = search_url
        self.courts_url = courts_url
        self.opinions_url = opinions_url
        self.timeout_seconds = timeout_seconds
        self.pause_seconds = max(0.0, pause_seconds)
        self.retries = max(1, int(retries))
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "Acquittify-Caselaw-Ingest/1.0"})
        if token:
            self._session.headers.update({"Authorization": f"Token {token}"})
        self._has_token = bool(token)

    def _request_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        backoff = 1.0
        for attempt in range(1, self.retries + 1):
            try:
                response = self._session.get(url, params=params, timeout=self.timeout_seconds)
                if response.status_code in {429, 500, 502, 503, 504}:
                    if attempt == self.retries:
                        response.raise_for_status()
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 20)
                    continue
                response.raise_for_status()
                payload = response.json()
                if self.pause_seconds:
                    time.sleep(self.pause_seconds)
                if not isinstance(payload, dict):
                    return {}
                return payload
            except requests.RequestException:
                if attempt == self.retries:
                    raise
                time.sleep(backoff)
                backoff = min(backoff * 2, 20)
        return {}

    def iter_federal_court_ids(self) -> list[str]:
        ids: list[str] = []
        seen: set[str] = set()
        next_url: str | None = self.courts_url
        params: dict[str, Any] | None = {"page_size": 500}

        while next_url:
            payload = self._request_json(next_url, params=params)
            params = None  # Cursor URL already includes query args.
            for record in payload.get("results", []) or []:
                if not isinstance(record, dict):
                    continue
                if not is_federal_court_record(record):
                    continue
                court_id = str(record.get("id") or "").strip().lower()
                if not court_id or court_id in seen:
                    continue
                seen.add(court_id)
                ids.append(court_id)
            raw_next = payload.get("next")
            next_url = str(raw_next).strip() if raw_next else None
        return ids

    def iter_daily_results(
        self,
        *,
        court_id: str,
        target_date: date,
        page_size: int,
        max_pages: int,
    ) -> Iterable[dict[str, Any]]:
        iso = target_date.isoformat()
        query = f"court_id:{court_id} AND dateFiled:[{iso} TO {iso}]"
        next_url: str | None = self.search_url
        params: dict[str, Any] | None = {
            "type": "o",
            "order_by": "dateFiled desc",
            "q": query,
            "page_size": max(1, min(int(page_size), 100)),
        }
        pages = 0

        while next_url and pages < max(1, max_pages):
            payload = self._request_json(next_url, params=params)
            params = None
            pages += 1
            for result in payload.get("results", []) or []:
                if isinstance(result, dict):
                    yield result
            raw_next = payload.get("next")
            next_url = str(raw_next).strip() if raw_next else None

    def fetch_opinion_detail(self, opinion_id: int | None) -> dict[str, Any] | None:
        if not opinion_id or not self._has_token:
            return None
        url = urljoin(self.opinions_url if self.opinions_url.endswith("/") else f"{self.opinions_url}/", f"{opinion_id}/")
        try:
            payload = self._request_json(url)
        except requests.HTTPError:
            return None
        return payload if isinstance(payload, dict) else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Nightly CourtListener federal criminal ingest")
    parser.add_argument(
        "--db-dsn",
        default=os.getenv("ACQ_CASELAW_DB_DSN") or os.getenv("COURTLISTENER_DB_DSN", ""),
        help="Postgres DSN (recommended: AWS RDS endpoint)",
    )
    parser.add_argument(
        "--courtlistener-token",
        default=os.getenv("COURTLISTENER_API_TOKEN"),
        help="CourtListener API token for opinion text endpoints",
    )
    parser.add_argument(
        "--timezone",
        default=os.getenv("ACQ_CASELAW_TIMEZONE", DEFAULT_TIMEZONE),
        help="Timezone used to compute 'today'",
    )
    parser.add_argument(
        "--max-runtime-hours",
        type=float,
        default=float(os.getenv("ACQ_CASELAW_RUNTIME_HOURS", str(DEFAULT_RUNTIME_HOURS))),
        help="Runtime budget for each nightly run",
    )
    parser.add_argument(
        "--state-key",
        default=os.getenv("ACQ_CASELAW_STATE_KEY", DEFAULT_STATE_KEY),
        help="State key in derived.caselaw_nightly_state",
    )
    parser.add_argument(
        "--taxonomy-path",
        type=Path,
        default=Path(os.getenv("ACQ_CASELAW_TAXONOMY_PATH", str(ROOT / "taxonomy" / "2026.01" / "taxonomy.yaml"))),
    )
    parser.add_argument(
        "--aliases-path",
        type=Path,
        default=Path(os.getenv("ACQ_CASELAW_ALIASES_PATH", str(ROOT / "taxonomy" / "2026.01" / "aliases.yaml"))),
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=Path(os.getenv("ACQ_CASELAW_LOG_PATH", str(ROOT / "reports" / "caselaw_nightly_ingest.jsonl"))),
    )
    parser.add_argument(
        "--exclude-quasi",
        action="store_true",
        help="Exclude quasi-criminal post-conviction decisions",
    )
    parser.add_argument(
        "--only-courts",
        default=os.getenv("ACQ_CASELAW_ONLY_COURTS", "").strip(),
        help="Comma-separated court ids to ingest (optional)",
    )
    parser.add_argument(
        "--backfill-start-date",
        default=os.getenv("ACQ_CASELAW_BACKFILL_START_DATE", "").strip(),
        help="Initial backfill date (YYYY-MM-DD) for first run",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=int(os.getenv("ACQ_CASELAW_PAGE_SIZE", "40")),
        help="CourtListener search page size",
    )
    parser.add_argument(
        "--max-pages-per-query",
        type=int,
        default=int(os.getenv("ACQ_CASELAW_MAX_PAGES_PER_QUERY", "40")),
        help="Max cursor pages per court/date query",
    )
    parser.add_argument(
        "--request-timeout-seconds",
        type=int,
        default=int(os.getenv("ACQ_CASELAW_REQUEST_TIMEOUT_SECONDS", "30")),
    )
    parser.add_argument(
        "--request-pause-seconds",
        type=float,
        default=float(os.getenv("ACQ_CASELAW_REQUEST_PAUSE_SECONDS", "0.1")),
    )
    parser.add_argument(
        "--request-retries",
        type=int,
        default=int(os.getenv("ACQ_CASELAW_REQUEST_RETRIES", "5")),
    )
    parser.add_argument(
        "--max-court-date-queries",
        type=int,
        default=int(os.getenv("ACQ_CASELAW_MAX_COURT_DATE_QUERIES", "0")),
        help="Optional hard cap on processed court/date queries per run (0 = unlimited)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write to the database",
    )
    return parser.parse_args()


def to_config(args: argparse.Namespace) -> Config:
    if not args.db_dsn and not args.dry_run:
        raise SystemExit("Missing --db-dsn (or set ACQ_CASELAW_DB_DSN/COURTLISTENER_DB_DSN).")

    only_courts: tuple[str, ...] | None = None
    if args.only_courts:
        parsed = [item.strip().lower() for item in str(args.only_courts).split(",") if item.strip()]
        if parsed:
            only_courts = tuple(parsed)

    backfill_start_date = parse_iso_date(args.backfill_start_date) if args.backfill_start_date else None

    aliases_path = Path(args.aliases_path) if args.aliases_path else None
    if aliases_path and not aliases_path.exists():
        aliases_path = None

    return Config(
        db_dsn=args.db_dsn,
        courtlistener_token=args.courtlistener_token,
        timezone_name=args.timezone,
        max_runtime_seconds=max(60, int(float(args.max_runtime_hours) * 3600)),
        state_key=args.state_key,
        taxonomy_path=Path(args.taxonomy_path),
        aliases_path=aliases_path,
        log_path=Path(args.log_path),
        include_quasi_criminal=not bool(args.exclude_quasi),
        only_courts=only_courts,
        backfill_start_date=backfill_start_date,
        page_size=max(1, min(int(args.page_size), 100)),
        max_pages_per_query=max(1, int(args.max_pages_per_query)),
        request_timeout_seconds=max(5, int(args.request_timeout_seconds)),
        request_pause_seconds=max(0.0, float(args.request_pause_seconds)),
        request_retries=max(1, int(args.request_retries)),
        max_court_date_queries=max(0, int(args.max_court_date_queries)),
        dry_run=bool(args.dry_run),
    )


def parse_iso_date(value: str | None) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def is_federal_court_record(record: dict[str, Any]) -> bool:
    return (
        str(record.get("jurisdiction") or "").upper() == "F"
        and bool(record.get("in_use", True))
        and bool(record.get("has_opinion_scraper", False))
    )


def order_federal_courts(court_ids: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    unique_ids: list[str] = []
    for court_id in court_ids:
        normalized = str(court_id or "").strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique_ids.append(normalized)

    priority = [court for court in PRIORITY_COURTS if court in seen]
    remaining = sorted(court for court in unique_ids if court not in PRIORITY_COURTS)
    return priority + remaining


def _normalize_synonyms(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            out.append(text)
    return out


def load_taxonomy_catalog(taxonomy_path: Path) -> tuple[str, list[TaxonomyNodeEntry], dict[str, str]]:
    if not taxonomy_path.exists():
        raise FileNotFoundError(f"Taxonomy file not found: {taxonomy_path}")
    payload = yaml.safe_load(taxonomy_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("Invalid taxonomy payload")

    version = str(payload.get("version") or "unknown")
    nodes_raw = payload.get("nodes") or []
    catalog: dict[str, str] = {}
    entries: list[TaxonomyNodeEntry] = []
    for node in nodes_raw:
        if not isinstance(node, dict):
            continue
        code = str(node.get("code") or "").strip()
        label = str(node.get("label") or "").strip()
        if code and label:
            catalog[code] = label
            entries.append(
                TaxonomyNodeEntry(
                    code=code,
                    label=label,
                    parent_code=None,
                    synonyms=_normalize_synonyms(node.get("synonyms")),
                )
            )

    codes = set(catalog)
    normalized_entries: list[TaxonomyNodeEntry] = []
    for entry in entries:
        parent_code = None
        if "." in entry.code:
            candidate = ".".join(entry.code.split(".")[:-1])
            if candidate and candidate in codes:
                parent_code = candidate
        normalized_entries.append(
            TaxonomyNodeEntry(
                code=entry.code,
                label=entry.label,
                parent_code=parent_code,
                synonyms=entry.synonyms,
            )
        )
    if not catalog:
        raise ValueError("No taxonomy nodes found")
    return version, normalized_entries, catalog


def choose_preferred_opinion(opinions: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not opinions:
        return None
    priority_order = {
        "combined": 0,
        "lead": 1,
        "majority": 2,
        "per curiam": 3,
        "unanimous": 4,
        "plurality": 5,
        "concurring": 6,
        "dissenting": 7,
    }

    def key_for(entry: dict[str, Any]) -> tuple[int, int]:
        opinion_type = str(entry.get("type") or "").strip().lower()
        pid = int(entry.get("id") or 0)
        return (priority_order.get(opinion_type, 999), -pid)

    best = sorted(opinions, key=key_for)
    return best[0] if best else None


def opinion_text_from_detail(payload: dict[str, Any] | None) -> str:
    if not payload:
        return ""
    for key in ("plain_text", "html_with_citations", "html", "opinion_text"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def opinion_text_from_search_item(item: dict[str, Any], preferred_opinion: dict[str, Any] | None) -> str:
    snippets: list[str] = []

    top_snippet = item.get("snippet")
    if isinstance(top_snippet, str) and top_snippet.strip():
        snippets.append(top_snippet)

    if preferred_opinion and isinstance(preferred_opinion.get("snippet"), str):
        value = str(preferred_opinion.get("snippet") or "")
        if value.strip():
            snippets.append(value)

    for entry in item.get("opinions", []) or []:
        if not isinstance(entry, dict):
            continue
        value = entry.get("snippet")
        if isinstance(value, str) and value.strip():
            snippets.append(value)
        if len(snippets) >= 4:
            break

    return "\n\n".join(snippets)


def normalize_opinion_text(raw_text: str) -> str:
    return clean_text(strip_html(str(raw_text or "")))


def extract_citations(item: dict[str, Any]) -> list[str]:
    citations = item.get("citation")
    if isinstance(citations, list):
        out: list[str] = []
        for entry in citations:
            if isinstance(entry, str) and entry.strip():
                out.append(entry.strip())
            elif isinstance(entry, dict):
                for key in ("cite", "citation", "volume_reporter_page"):
                    value = entry.get(key)
                    if isinstance(value, str) and value.strip():
                        out.append(value.strip())
                        break
        return sorted(set(out))
    return []


def classify_case_type(
    *,
    case_name: str,
    docket_number: str,
    citations: list[str],
    opinion_text: str,
) -> tuple[str, str]:
    combined = "\n".join([
        case_name,
        docket_number,
        " ".join(citations),
        opinion_text[:12000],
    ])

    for pattern in QUASI_CRIMINAL_PATTERNS:
        if pattern.search(combined):
            return "quasi_criminal", f"matched quasi-criminal pattern: {pattern.pattern}"

    for pattern in CRIMINAL_PATTERNS:
        if pattern.search(combined):
            return "criminal", f"matched criminal pattern: {pattern.pattern}"

    return "non_criminal", "no criminal or quasi-criminal indicators matched"


def include_case(case_type: str, include_quasi_criminal: bool) -> bool:
    if case_type == "criminal":
        return True
    if case_type == "quasi_criminal":
        return include_quasi_criminal
    return False


def fallback_taxonomy_entries(text: str, taxonomy_catalog: dict[str, str]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for pattern, code in FALLBACK_TAXONOMY_RULES:
        if code not in taxonomy_catalog:
            continue
        if pattern.search(text):
            out.append({"code": code, "label": taxonomy_catalog[code]})
        if len(out) >= 3:
            break

    if out:
        return out

    fallback_code = DEFAULT_FALLBACK_CODE if DEFAULT_FALLBACK_CODE in taxonomy_catalog else sorted(taxonomy_catalog)[0]
    return [{"code": fallback_code, "label": taxonomy_catalog[fallback_code]}]


def dedupe_taxonomy_entries(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    result: list[dict[str, str]] = []
    for entry in entries:
        code = str(entry.get("code") or "").strip()
        label = str(entry.get("label") or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        result.append({"code": code, "label": label})
    return result


def taxonomy_entries_from_frontmatter(frontmatter: dict[str, Any], taxonomy_catalog: dict[str, str]) -> list[dict[str, str]]:
    raw_entries = frontmatter.get("case_taxonomies")
    if not isinstance(raw_entries, list):
        return []
    entries: list[dict[str, str]] = []
    for raw in raw_entries:
        code = ""
        label = ""
        if isinstance(raw, dict):
            code = str(raw.get("code") or "").strip()
            label = str(raw.get("label") or "").strip()
        elif isinstance(raw, str):
            code = raw.strip()
        if not code:
            continue
        if not label:
            label = taxonomy_catalog.get(code, "")
        entries.append({"code": code, "label": label})
    return dedupe_taxonomy_entries(entries)


def summarize(text: str, max_chars: int) -> str:
    compact = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(compact) <= max_chars:
        return compact
    return compact[: max(0, max_chars - 3)].rstrip() + "..."


def infer_court_level(court_id: str, court_name: str) -> str:
    cid = str(court_id or "").strip().lower()
    cname = str(court_name or "").strip().lower()
    if cid == "scotus" or "supreme court" in cname:
        return "supreme"
    if cid == "cafc" or cid.startswith("ca") or "circuit" in cname or "appeals" in cname:
        return "circuit"
    if "district" in cname:
        return "district"
    return "other"


def to_absolute_courtlistener_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    if raw.startswith("/"):
        return f"https://www.courtlistener.com{raw}"
    return f"https://www.courtlistener.com/{raw}"


def build_case_frontmatter(
    *,
    cluster_id: int,
    opinion_id: int | None,
    case_name: str,
    court_id: str,
    court_name: str,
    date_filed: str,
    docket_number: str,
    citations: list[str],
    case_type: str,
    taxonomy_entries: list[dict[str, str]],
    taxonomy_version: str,
    opinion_text: str,
    publication_status: str,
    opinion_type: str,
    absolute_url: str,
    reason: str,
) -> dict[str, Any]:
    summary = summarize(opinion_text, 1200)
    essential_holding = summarize(opinion_text, 1800)
    case_id = f"case.courtlistener.cluster.{cluster_id}"

    return {
        "type": "case",
        "case_id": case_id,
        "title": case_name,
        "court": court_name,
        "court_level": infer_court_level(court_id, court_name),
        "jurisdiction": "US",
        "date_decided": date_filed,
        "publication_status": publication_status,
        "opinion_type": opinion_type,
        "originating_circuit": court_id,
        "judges": {},
        "citations_in_text": citations,
        "case_summary": summary,
        "essential_holding": essential_holding,
        "case_taxonomies": taxonomy_entries,
        "sources": {
            "source": "courtlistener",
            "courtlistener_cluster_id": cluster_id,
            "courtlistener_opinion_id": opinion_id,
            "opinion_url": absolute_url,
            "primary_citation": citations[0] if citations else "",
            "docket_number": docket_number,
        },
        "ingestion": {
            "pipeline": "nightly_federal_criminal_caselaw",
            "ingested_at": utc_now().isoformat(),
            "case_type": case_type,
            "case_type_reason": reason,
            "taxonomy_version": taxonomy_version,
        },
    }


def frontmatter_to_yaml(frontmatter: dict[str, Any]) -> str:
    return yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=False).strip() + "\n"


def normalize_case_date(value: str | None, fallback: date | None = None) -> str:
    raw = str(value or "").strip()
    default_date = fallback or date(1900, 1, 1)
    if not raw:
        return default_date.isoformat()
    if re.fullmatch(r"\d{4}", raw):
        year = int(raw)
        if year < 1:
            return default_date.isoformat()
        return f"{year:04d}-01-01"
    direct = parse_iso_date(raw)
    if direct:
        return direct.isoformat()
    if len(raw) >= 10:
        direct = parse_iso_date(raw[:10])
        if direct:
            return direct.isoformat()
    year_match = re.search(r"(19|20)\d{2}", raw)
    if year_match:
        return f"{year_match.group(0)}-01-01"
    return default_date.isoformat()


def extract_year(date_filed: str | None) -> int:
    normalized = normalize_case_date(date_filed)
    try:
        return int(normalized[:4])
    except Exception:
        return utc_now().year


def infer_authority_weight(court_id: str, court_name: str) -> int:
    cid = str(court_id or "").strip().lower()
    cname = str(court_name or "").strip().lower()
    if cid == "scotus" or "supreme court" in cname:
        return 100
    if cid == "cafc":
        return 92
    if cid.startswith("ca") or "circuit" in cname or "appeals" in cname:
        return 86
    if "district" in cname:
        return 72
    return 60


def synthetic_negative_id(seed: str) -> int:
    digest = hashlib.sha256(str(seed).encode("utf-8")).hexdigest()
    # Keep in BIGINT range and reserve negative space for non-CourtListener records.
    return -1 * (int(digest[:15], 16) + 1)


def resolve_source_opinion_id(
    *,
    opinion_id: int | None,
    cluster_id: int | None,
    case_id: str,
) -> int:
    if opinion_id is not None:
        return int(opinion_id)
    if cluster_id is not None:
        return int(cluster_id)
    return synthetic_negative_id(case_id)


def build_legal_unit_payloads(
    *,
    case_id: str,
    taxonomy_codes: list[str],
    taxonomy_version: str,
    court_id: str,
    court_name: str,
    date_filed: str,
    frontmatter: dict[str, Any],
    opinion_text: str,
    source_opinion_id: int,
    ingestion_batch_id: str,
) -> list[dict[str, Any]]:
    codes: list[str] = []
    seen_codes: set[str] = set()
    for code in taxonomy_codes:
        normalized = str(code or "").strip()
        if not normalized or normalized in seen_codes:
            continue
        seen_codes.add(normalized)
        codes.append(normalized)

    if not codes:
        return []

    court_level = infer_court_level(court_id, court_name)
    year = extract_year(date_filed)
    authority_weight = infer_authority_weight(court_id, court_name)
    core_text = (
        str(frontmatter.get("essential_holding") or "").strip()
        or str(frontmatter.get("case_summary") or "").strip()
        or str(opinion_text or "").strip()
        or str(frontmatter.get("title") or case_id)
    )
    unit_text = summarize(core_text, 4000)
    if not unit_text:
        unit_text = str(frontmatter.get("title") or case_id)

    output: list[dict[str, Any]] = []
    for code in codes:
        secondary_codes = [other for other in codes if other != code]
        unit_id = uuid.uuid5(uuid.NAMESPACE_URL, f"acquittify:caselaw:{case_id}:{code}")
        output.append(
            {
                "unit_id": unit_id,
                "unit_type": "HOLDING",
                "taxonomy_code": code,
                "taxonomy_version": taxonomy_version,
                "circuit": str(court_id or "unknown"),
                "court_level": court_level,
                "year": year,
                "posture": "UNKNOWN",
                "standard_of_review": "UNKNOWN",
                "burden": "UNKNOWN",
                "is_holding": True,
                "is_dicta": False,
                "favorability": 0,
                "authority_weight": authority_weight,
                "secondary_taxonomy_ids": secondary_codes,
                "standard_unit_ids": [],
                "unit_text": unit_text,
                "source_opinion_id": source_opinion_id,
                "ingestion_batch_id": ingestion_batch_id,
            }
        )
    return output


class CaseStore:
    """Postgres persistence for nightly caselaw ingest."""

    def __init__(self, dsn: str, dry_run: bool = False) -> None:
        self.dsn = dsn
        self.dry_run = dry_run

    def connect(self):
        return psycopg.connect(self.dsn)

    @staticmethod
    def init_schema(conn) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE SCHEMA IF NOT EXISTS derived;

                CREATE TABLE IF NOT EXISTS derived.caselaw_nightly_case (
                    id BIGSERIAL PRIMARY KEY,
                    case_id TEXT NOT NULL UNIQUE,
                    courtlistener_cluster_id BIGINT NOT NULL UNIQUE,
                    courtlistener_opinion_id BIGINT,
                    court_id TEXT NOT NULL,
                    court_name TEXT,
                    date_filed DATE,
                    docket_number TEXT,
                    case_name TEXT NOT NULL,
                    case_type TEXT NOT NULL,
                    taxonomy_codes TEXT[] NOT NULL DEFAULT '{}'::text[],
                    taxonomy_version TEXT NOT NULL,
                    frontmatter_yaml TEXT NOT NULL,
                    frontmatter_json JSONB NOT NULL,
                    opinion_text TEXT,
                    opinion_text_sha256 TEXT,
                    source_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                    first_ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    last_ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS caselaw_nightly_case_date_idx
                    ON derived.caselaw_nightly_case (date_filed DESC);

                CREATE INDEX IF NOT EXISTS caselaw_nightly_case_court_idx
                    ON derived.caselaw_nightly_case (court_id, date_filed DESC);

                CREATE INDEX IF NOT EXISTS caselaw_nightly_case_type_idx
                    ON derived.caselaw_nightly_case (case_type);

                CREATE INDEX IF NOT EXISTS caselaw_nightly_case_taxonomy_gin
                    ON derived.caselaw_nightly_case USING GIN (taxonomy_codes);

                CREATE TABLE IF NOT EXISTS derived.caselaw_nightly_state (
                    state_key TEXT PRIMARY KEY,
                    backfill_cursor_date DATE NOT NULL,
                    backfill_court_index INTEGER NOT NULL DEFAULT 0,
                    last_run_started_at TIMESTAMPTZ,
                    last_run_finished_at TIMESTAMPTZ,
                    last_run_status TEXT,
                    last_run_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS derived.taxonomy_node (
                    id BIGSERIAL PRIMARY KEY,
                    code TEXT NOT NULL,
                    version TEXT NOT NULL,
                    label TEXT NOT NULL,
                    parent_code TEXT NULL,
                    synonyms JSONB NOT NULL DEFAULT '[]'::jsonb,
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    deprecated_at TIMESTAMPTZ NULL,
                    replaced_by_code TEXT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (code, version),
                    CHECK (status IN ('ACTIVE', 'DEPRECATED', 'EXPERIMENTAL'))
                );

                CREATE INDEX IF NOT EXISTS taxonomy_node_version_idx
                    ON derived.taxonomy_node (version, code);

                CREATE TABLE IF NOT EXISTS derived.legal_unit (
                    id BIGSERIAL PRIMARY KEY,
                    unit_id UUID NOT NULL UNIQUE,
                    unit_type TEXT NOT NULL,
                    taxonomy_code TEXT NOT NULL,
                    taxonomy_version TEXT NOT NULL,
                    circuit TEXT NOT NULL,
                    court_level TEXT,
                    year INTEGER NOT NULL,
                    posture TEXT NOT NULL,
                    standard_of_review TEXT NOT NULL,
                    burden TEXT NOT NULL,
                    is_holding BOOLEAN NOT NULL,
                    is_dicta BOOLEAN NOT NULL,
                    favorability INTEGER NOT NULL DEFAULT 0,
                    authority_weight INTEGER NOT NULL DEFAULT 0,
                    secondary_taxonomy_ids TEXT[] NOT NULL DEFAULT '{}'::text[],
                    standard_unit_ids UUID[] NOT NULL DEFAULT '{}'::uuid[],
                    unit_text TEXT NOT NULL,
                    source_opinion_id BIGINT NOT NULL,
                    ingestion_batch_id TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS legal_unit_taxonomy_idx
                    ON derived.legal_unit (taxonomy_version, taxonomy_code);

                CREATE INDEX IF NOT EXISTS legal_unit_circuit_year_idx
                    ON derived.legal_unit (circuit, year DESC);

                CREATE INDEX IF NOT EXISTS legal_unit_source_idx
                    ON derived.legal_unit (source_opinion_id);

                CREATE INDEX IF NOT EXISTS legal_unit_secondary_taxonomy_gin
                    ON derived.legal_unit USING GIN (secondary_taxonomy_ids);

                CREATE TABLE IF NOT EXISTS derived.job_run (
                    job_name TEXT PRIMARY KEY,
                    last_raw_id BIGINT NOT NULL DEFAULT 0,
                    batch_size INTEGER NOT NULL DEFAULT 25,
                    last_run_at TIMESTAMPTZ,
                    last_status TEXT,
                    last_error TEXT,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
        conn.commit()

    @staticmethod
    def load_state(conn, state_key: str, default_cursor_date: date) -> dict[str, Any]:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT state_key, backfill_cursor_date, backfill_court_index,
                       last_run_started_at, last_run_finished_at,
                       last_run_status, last_run_summary
                FROM derived.caselaw_nightly_state
                WHERE state_key = %s
                """,
                (state_key,),
            )
            row = cur.fetchone()
            if row:
                return dict(row)

            cur.execute(
                """
                INSERT INTO derived.caselaw_nightly_state (
                    state_key, backfill_cursor_date, backfill_court_index, last_run_status, last_run_summary
                ) VALUES (%s, %s, 0, 'initialized', '{}'::jsonb)
                RETURNING state_key, backfill_cursor_date, backfill_court_index,
                          last_run_started_at, last_run_finished_at,
                          last_run_status, last_run_summary
                """,
                (state_key, default_cursor_date),
            )
            created = cur.fetchone()
        conn.commit()
        return dict(created or {})

    @staticmethod
    def save_state(
        conn,
        *,
        state_key: str,
        backfill_cursor_date: date,
        backfill_court_index: int,
        last_run_started_at: datetime,
        last_run_finished_at: datetime,
        last_run_status: str,
        last_run_summary: dict[str, Any],
    ) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO derived.caselaw_nightly_state (
                    state_key,
                    backfill_cursor_date,
                    backfill_court_index,
                    last_run_started_at,
                    last_run_finished_at,
                    last_run_status,
                    last_run_summary,
                    updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, NOW())
                ON CONFLICT (state_key)
                DO UPDATE SET
                    backfill_cursor_date = EXCLUDED.backfill_cursor_date,
                    backfill_court_index = EXCLUDED.backfill_court_index,
                    last_run_started_at = EXCLUDED.last_run_started_at,
                    last_run_finished_at = EXCLUDED.last_run_finished_at,
                    last_run_status = EXCLUDED.last_run_status,
                    last_run_summary = EXCLUDED.last_run_summary,
                    updated_at = NOW();
                """,
                (
                    state_key,
                    backfill_cursor_date,
                    backfill_court_index,
                    last_run_started_at,
                    last_run_finished_at,
                    last_run_status,
                    json.dumps(last_run_summary, ensure_ascii=False),
                ),
            )
        conn.commit()

    @staticmethod
    def upsert_case(conn, payload: dict[str, Any], *, commit: bool = True) -> str:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO derived.caselaw_nightly_case (
                    case_id,
                    courtlistener_cluster_id,
                    courtlistener_opinion_id,
                    court_id,
                    court_name,
                    date_filed,
                    docket_number,
                    case_name,
                    case_type,
                    taxonomy_codes,
                    taxonomy_version,
                    frontmatter_yaml,
                    frontmatter_json,
                    opinion_text,
                    opinion_text_sha256,
                    source_payload,
                    first_ingested_at,
                    last_ingested_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s::text[], %s, %s, %s::jsonb, %s, %s, %s::jsonb,
                    NOW(), NOW()
                )
                ON CONFLICT (courtlistener_cluster_id)
                DO UPDATE SET
                    case_id = EXCLUDED.case_id,
                    courtlistener_opinion_id = EXCLUDED.courtlistener_opinion_id,
                    court_id = EXCLUDED.court_id,
                    court_name = EXCLUDED.court_name,
                    date_filed = EXCLUDED.date_filed,
                    docket_number = EXCLUDED.docket_number,
                    case_name = EXCLUDED.case_name,
                    case_type = EXCLUDED.case_type,
                    taxonomy_codes = EXCLUDED.taxonomy_codes,
                    taxonomy_version = EXCLUDED.taxonomy_version,
                    frontmatter_yaml = EXCLUDED.frontmatter_yaml,
                    frontmatter_json = EXCLUDED.frontmatter_json,
                    opinion_text = EXCLUDED.opinion_text,
                    opinion_text_sha256 = EXCLUDED.opinion_text_sha256,
                    source_payload = EXCLUDED.source_payload,
                    last_ingested_at = NOW()
                RETURNING CASE WHEN xmax = 0 THEN 'inserted' ELSE 'updated' END;
                """,
                (
                    payload["case_id"],
                    payload["courtlistener_cluster_id"],
                    payload.get("courtlistener_opinion_id"),
                    payload["court_id"],
                    payload.get("court_name"),
                    payload.get("date_filed"),
                    payload.get("docket_number"),
                    payload["case_name"],
                    payload["case_type"],
                    payload["taxonomy_codes"],
                    payload["taxonomy_version"],
                    payload["frontmatter_yaml"],
                    json.dumps(payload["frontmatter_json"], ensure_ascii=False),
                    payload.get("opinion_text"),
                    payload.get("opinion_text_sha256"),
                    json.dumps(payload.get("source_payload") or {}, ensure_ascii=False),
                ),
            )
            row = cur.fetchone()
        if commit:
            conn.commit()
        return str(row[0]) if row and row[0] else "updated"

    @staticmethod
    def upsert_taxonomy_nodes(
        conn,
        *,
        version: str,
        nodes: list[TaxonomyNodeEntry],
        commit: bool = True,
    ) -> int:
        if not nodes:
            return 0
        with conn.cursor() as cur:
            for node in nodes:
                cur.execute(
                    """
                    INSERT INTO derived.taxonomy_node (
                        code,
                        version,
                        label,
                        parent_code,
                        synonyms,
                        updated_at
                    ) VALUES (%s, %s, %s, %s, %s::jsonb, NOW())
                    ON CONFLICT (code, version)
                    DO UPDATE SET
                        label = EXCLUDED.label,
                        parent_code = EXCLUDED.parent_code,
                        synonyms = EXCLUDED.synonyms,
                        updated_at = NOW();
                    """,
                    (
                        node.code,
                        version,
                        node.label,
                        node.parent_code,
                        json.dumps(node.synonyms, ensure_ascii=False),
                    ),
                )
        if commit:
            conn.commit()
        return len(nodes)

    @staticmethod
    def upsert_legal_units(conn, units: list[dict[str, Any]], *, commit: bool = True) -> tuple[int, int]:
        if not units:
            return (0, 0)
        inserted = 0
        updated = 0
        with conn.cursor() as cur:
            for unit in units:
                cur.execute(
                    """
                    INSERT INTO derived.legal_unit (
                        unit_id,
                        unit_type,
                        taxonomy_code,
                        taxonomy_version,
                        circuit,
                        court_level,
                        year,
                        posture,
                        standard_of_review,
                        burden,
                        is_holding,
                        is_dicta,
                        favorability,
                        authority_weight,
                        secondary_taxonomy_ids,
                        standard_unit_ids,
                        unit_text,
                        source_opinion_id,
                        ingestion_batch_id,
                        created_at,
                        updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s::text[], %s::uuid[], %s, %s, %s, NOW(), NOW()
                    )
                    ON CONFLICT (unit_id)
                    DO UPDATE SET
                        unit_type = EXCLUDED.unit_type,
                        taxonomy_code = EXCLUDED.taxonomy_code,
                        taxonomy_version = EXCLUDED.taxonomy_version,
                        circuit = EXCLUDED.circuit,
                        court_level = EXCLUDED.court_level,
                        year = EXCLUDED.year,
                        posture = EXCLUDED.posture,
                        standard_of_review = EXCLUDED.standard_of_review,
                        burden = EXCLUDED.burden,
                        is_holding = EXCLUDED.is_holding,
                        is_dicta = EXCLUDED.is_dicta,
                        favorability = EXCLUDED.favorability,
                        authority_weight = EXCLUDED.authority_weight,
                        secondary_taxonomy_ids = EXCLUDED.secondary_taxonomy_ids,
                        standard_unit_ids = EXCLUDED.standard_unit_ids,
                        unit_text = EXCLUDED.unit_text,
                        source_opinion_id = EXCLUDED.source_opinion_id,
                        ingestion_batch_id = EXCLUDED.ingestion_batch_id,
                        updated_at = NOW()
                    RETURNING CASE WHEN xmax = 0 THEN 'inserted' ELSE 'updated' END;
                    """,
                    (
                        unit["unit_id"],
                        unit["unit_type"],
                        unit["taxonomy_code"],
                        unit["taxonomy_version"],
                        unit["circuit"],
                        unit.get("court_level"),
                        int(unit["year"]),
                        unit["posture"],
                        unit["standard_of_review"],
                        unit["burden"],
                        bool(unit["is_holding"]),
                        bool(unit["is_dicta"]),
                        int(unit["favorability"]),
                        int(unit["authority_weight"]),
                        list(unit.get("secondary_taxonomy_ids") or []),
                        list(unit.get("standard_unit_ids") or []),
                        unit["unit_text"],
                        int(unit["source_opinion_id"]),
                        unit.get("ingestion_batch_id"),
                    ),
                )
                row = cur.fetchone()
                if row and row[0] == "inserted":
                    inserted += 1
                else:
                    updated += 1
        if commit:
            conn.commit()
        return inserted, updated


def append_log(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def process_court_date(
    *,
    client: CourtListenerClient,
    conn,
    config: Config,
    taxonomy_version: str,
    taxonomy_catalog: dict[str, str],
    ingestion_batch_id: str,
    court_id: str,
    target_date: date,
    deadline_utc: datetime,
    seen_cluster_ids: set[int],
) -> dict[str, Any]:
    counters = {
        "court_id": court_id,
        "date": target_date.isoformat(),
        "scanned": 0,
        "inserted": 0,
        "updated": 0,
        "ontology_units_inserted": 0,
        "ontology_units_updated": 0,
        "skipped_duplicates": 0,
        "skipped_non_criminal": 0,
        "errors": 0,
        "completed": True,
        "timed_out": False,
    }

    for item in client.iter_daily_results(
        court_id=court_id,
        target_date=target_date,
        page_size=config.page_size,
        max_pages=config.max_pages_per_query,
    ):
        if utc_now() >= deadline_utc:
            counters["completed"] = False
            counters["timed_out"] = True
            break

        counters["scanned"] += 1
        raw_cluster_id = item.get("cluster_id") or item.get("id")
        try:
            cluster_id = int(raw_cluster_id)
        except Exception:
            counters["errors"] += 1
            continue

        if cluster_id in seen_cluster_ids:
            counters["skipped_duplicates"] += 1
            continue

        seen_cluster_ids.add(cluster_id)

        opinions = item.get("opinions") or []
        opinions = opinions if isinstance(opinions, list) else []
        preferred_opinion = choose_preferred_opinion([p for p in opinions if isinstance(p, dict)])
        opinion_id = None
        if preferred_opinion and preferred_opinion.get("id") is not None:
            try:
                opinion_id = int(preferred_opinion.get("id"))
            except Exception:
                opinion_id = None

        opinion_detail = client.fetch_opinion_detail(opinion_id)
        raw_text = opinion_text_from_detail(opinion_detail)
        if not raw_text:
            raw_text = opinion_text_from_search_item(item, preferred_opinion)
        opinion_text = normalize_opinion_text(raw_text)

        case_name = str(item.get("caseName") or item.get("case_name") or f"Cluster {cluster_id}").strip()
        docket_number = str(item.get("docketNumber") or item.get("docket_number") or "").strip()
        citations = extract_citations(item)

        case_type, case_type_reason = classify_case_type(
            case_name=case_name,
            docket_number=docket_number,
            citations=citations,
            opinion_text=opinion_text,
        )
        if not include_case(case_type, config.include_quasi_criminal):
            counters["skipped_non_criminal"] += 1
            continue

        taxonomy_entries = map_case_taxonomies(
            title=case_name,
            case_summary=summarize(opinion_text, 1600),
            essential_holding=summarize(opinion_text, 2000),
            opinion_text=opinion_text,
            taxonomy_path=config.taxonomy_path,
            aliases_path=config.aliases_path,
            max_results=12,
        )
        if not taxonomy_entries:
            taxonomy_entries = fallback_taxonomy_entries(opinion_text, taxonomy_catalog)
        taxonomy_entries = dedupe_taxonomy_entries(taxonomy_entries)

        court_name = str(item.get("court") or "").strip() or court_id
        date_filed = str(item.get("dateFiled") or item.get("date_filed") or target_date.isoformat()).strip()
        publication_status = str(item.get("status") or "").strip()
        opinion_type = str((preferred_opinion or {}).get("type") or "").strip()
        absolute_url = to_absolute_courtlistener_url(str(item.get("absolute_url") or ""))

        frontmatter = build_case_frontmatter(
            cluster_id=cluster_id,
            opinion_id=opinion_id,
            case_name=case_name,
            court_id=court_id,
            court_name=court_name,
            date_filed=date_filed,
            docket_number=docket_number,
            citations=citations,
            case_type=case_type,
            taxonomy_entries=taxonomy_entries,
            taxonomy_version=taxonomy_version,
            opinion_text=opinion_text,
            publication_status=publication_status,
            opinion_type=opinion_type,
            absolute_url=absolute_url,
            reason=case_type_reason,
        )
        frontmatter_yaml = frontmatter_to_yaml(frontmatter)
        taxonomy_codes = [entry["code"] for entry in taxonomy_entries if entry.get("code")]

        payload = {
            "case_id": frontmatter["case_id"],
            "courtlistener_cluster_id": cluster_id,
            "courtlistener_opinion_id": opinion_id,
            "court_id": court_id,
            "court_name": court_name,
            "date_filed": normalize_case_date(date_filed, fallback=target_date),
            "docket_number": docket_number,
            "case_name": case_name,
            "case_type": case_type,
            "taxonomy_codes": taxonomy_codes,
            "taxonomy_version": taxonomy_version,
            "frontmatter_yaml": frontmatter_yaml,
            "frontmatter_json": frontmatter,
            "opinion_text": opinion_text,
            "opinion_text_sha256": hashlib.sha256(opinion_text.encode("utf-8")).hexdigest() if opinion_text else "",
            "source_payload": {
                "search_result": item,
                "preferred_opinion": preferred_opinion or {},
                "opinion_detail": opinion_detail or {},
            },
        }

        if config.dry_run:
            counters["inserted"] += 1
            counters["ontology_units_inserted"] += len(taxonomy_codes)
            continue

        try:
            status = CaseStore.upsert_case(conn, payload)
            if status == "inserted":
                counters["inserted"] += 1
            else:
                counters["updated"] += 1

            source_opinion_id = resolve_source_opinion_id(
                opinion_id=payload.get("courtlistener_opinion_id"),
                cluster_id=payload.get("courtlistener_cluster_id"),
                case_id=payload["case_id"],
            )
            legal_units = build_legal_unit_payloads(
                case_id=payload["case_id"],
                taxonomy_codes=taxonomy_codes,
                taxonomy_version=taxonomy_version,
                court_id=court_id,
                court_name=court_name,
                date_filed=str(payload.get("date_filed") or ""),
                frontmatter=frontmatter,
                opinion_text=opinion_text,
                source_opinion_id=source_opinion_id,
                ingestion_batch_id=ingestion_batch_id,
            )
            lu_inserted, lu_updated = CaseStore.upsert_legal_units(conn, legal_units)
            counters["ontology_units_inserted"] += lu_inserted
            counters["ontology_units_updated"] += lu_updated
        except Exception:
            counters["errors"] += 1

    return counters


def merge_counts(destination: dict[str, int], payload: dict[str, Any]) -> None:
    for key in (
        "scanned",
        "inserted",
        "updated",
        "ontology_units_inserted",
        "ontology_units_updated",
        "skipped_duplicates",
        "skipped_non_criminal",
        "errors",
    ):
        destination[key] = destination.get(key, 0) + int(payload.get(key, 0) or 0)


def run(config: Config) -> dict[str, Any]:
    timezone_obj = ZoneInfo(config.timezone_name)
    today_local = datetime.now(timezone_obj).date()
    default_backfill_date = config.backfill_start_date or (today_local - timedelta(days=1))

    taxonomy_version, taxonomy_nodes, taxonomy_catalog = load_taxonomy_catalog(config.taxonomy_path)

    client = CourtListenerClient(
        token=config.courtlistener_token,
        timeout_seconds=config.request_timeout_seconds,
        pause_seconds=config.request_pause_seconds,
        retries=config.request_retries,
    )

    court_ids = list(config.only_courts or ())
    if not court_ids:
        court_ids = client.iter_federal_court_ids()
    ordered_courts = order_federal_courts(court_ids)
    if not ordered_courts:
        ordered_courts = ["scotus", "cafc"]

    priority_courts = [court for court in PRIORITY_COURTS if court in ordered_courts]
    backfill_courts = ordered_courts

    started_at = utc_now()
    deadline_utc = started_at + timedelta(seconds=config.max_runtime_seconds)
    ingestion_batch_id = f"nightly_caselaw:{started_at.strftime('%Y%m%dT%H%M%SZ')}"

    totals: dict[str, int] = {
        "scanned": 0,
        "inserted": 0,
        "updated": 0,
        "ontology_units_inserted": 0,
        "ontology_units_updated": 0,
        "skipped_duplicates": 0,
        "skipped_non_criminal": 0,
        "errors": 0,
    }
    run_steps: list[dict[str, Any]] = []
    step_count = 0
    max_steps_in_summary = 100
    max_queries_reached = False
    seen_cluster_ids: set[int] = set()
    taxonomy_nodes_loaded = 0

    if config.dry_run:
        conn = psycopg.connect(config.db_dsn) if config.db_dsn else None
    else:
        conn = psycopg.connect(config.db_dsn)

    try:
        if conn is not None:
            CaseStore.init_schema(conn)
            if not config.dry_run:
                taxonomy_nodes_loaded = CaseStore.upsert_taxonomy_nodes(
                    conn,
                    version=taxonomy_version,
                    nodes=taxonomy_nodes,
                )

        state = {
            "backfill_cursor_date": default_backfill_date,
            "backfill_court_index": 0,
        }
        if conn is not None and not config.dry_run:
            db_state = CaseStore.load_state(conn, config.state_key, default_backfill_date)
            state["backfill_cursor_date"] = db_state.get("backfill_cursor_date") or default_backfill_date
            state["backfill_court_index"] = int(db_state.get("backfill_court_index") or 0)

        backfill_cursor_date = state["backfill_cursor_date"]
        if isinstance(backfill_cursor_date, datetime):
            backfill_cursor_date = backfill_cursor_date.date()
        if not isinstance(backfill_cursor_date, date):
            backfill_cursor_date = default_backfill_date
        backfill_court_index = max(0, min(int(state["backfill_court_index"]), max(0, len(backfill_courts) - 1)))

        if backfill_cursor_date >= today_local:
            backfill_cursor_date = today_local - timedelta(days=1)
            backfill_court_index = 0

        # Step 1: today's SCOTUS then Federal Circuit
        for court_id in priority_courts:
            if config.max_court_date_queries and step_count >= config.max_court_date_queries:
                max_queries_reached = True
                break
            if utc_now() >= deadline_utc:
                break
            result = process_court_date(
                client=client,
                conn=conn,
                config=config,
                taxonomy_version=taxonomy_version,
                taxonomy_catalog=taxonomy_catalog,
                ingestion_batch_id=ingestion_batch_id,
                court_id=court_id,
                target_date=today_local,
                deadline_utc=deadline_utc,
                seen_cluster_ids=seen_cluster_ids,
            )
            step_count += 1
            if len(run_steps) < max_steps_in_summary:
                run_steps.append(result)
            merge_counts(totals, result)

        timed_out = utc_now() >= deadline_utc

        # Step 2: backward backfill across federal courts
        while not timed_out and backfill_courts:
            if config.max_court_date_queries and step_count >= config.max_court_date_queries:
                max_queries_reached = True
                break
            court_id = backfill_courts[backfill_court_index]
            result = process_court_date(
                client=client,
                conn=conn,
                config=config,
                taxonomy_version=taxonomy_version,
                taxonomy_catalog=taxonomy_catalog,
                ingestion_batch_id=ingestion_batch_id,
                court_id=court_id,
                target_date=backfill_cursor_date,
                deadline_utc=deadline_utc,
                seen_cluster_ids=seen_cluster_ids,
            )
            step_count += 1
            if len(run_steps) < max_steps_in_summary:
                run_steps.append(result)
            merge_counts(totals, result)

            if result.get("timed_out"):
                timed_out = True
                break

            # Advance cursor only after a completed court/day scan.
            if result.get("completed"):
                backfill_court_index += 1
                if backfill_court_index >= len(backfill_courts):
                    backfill_court_index = 0
                    backfill_cursor_date = backfill_cursor_date - timedelta(days=1)

            timed_out = utc_now() >= deadline_utc

        finished_at = utc_now()
        status = "timed_out" if timed_out else "ok"
        if max_queries_reached:
            status = "max_queries_reached"

        summary = {
            "event": "caselaw_nightly_summary",
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "status": status,
            "timezone": config.timezone_name,
            "today_local": today_local.isoformat(),
            "priority_courts": priority_courts,
            "ordered_courts": ordered_courts,
            "backfill_cursor_date": backfill_cursor_date.isoformat(),
            "backfill_court_index": backfill_court_index,
            "dry_run": config.dry_run,
            "taxonomy_version": taxonomy_version,
            "taxonomy_nodes_loaded": taxonomy_nodes_loaded,
            "ingestion_batch_id": ingestion_batch_id,
            **totals,
            "step_count": step_count,
            "steps_truncated": step_count > len(run_steps),
            "max_court_date_queries": config.max_court_date_queries,
            "steps": run_steps,
        }

        append_log(config.log_path, summary)

        if conn is not None and not config.dry_run:
            CaseStore.save_state(
                conn,
                state_key=config.state_key,
                backfill_cursor_date=backfill_cursor_date,
                backfill_court_index=backfill_court_index,
                last_run_started_at=started_at,
                last_run_finished_at=finished_at,
                last_run_status=status,
                last_run_summary=summary,
            )

        return summary
    finally:
        if conn is not None:
            conn.close()


def main() -> int:
    config = to_config(parse_args())
    summary = run(config)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
