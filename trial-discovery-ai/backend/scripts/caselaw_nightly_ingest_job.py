#!/usr/bin/env python3
"""Stateful caselaw ingest job for ECS/EventBridge scheduling.

Design goals:
- No request-path side effects in API routes.
- Safe chunked execution for frequent scheduler triggers.
- Cursor/state persisted in derived.caselaw_nightly_state.
- Works in backend container image (no repo-root script dependency).
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

DEFAULT_SEARCH_URL = "https://www.courtlistener.com/api/rest/v4/search/"
DEFAULT_COURTS_URL = "https://www.courtlistener.com/api/rest/v4/courts/"
DEFAULT_OPINIONS_URL = "https://www.courtlistener.com/api/rest/v4/opinions/"
DEFAULT_STATE_KEY = "courtlistener_federal_criminal_nightly"
DEFAULT_TIMEZONE = "America/Detroit"
DEFAULT_RUNTIME_HOURS = 0.33
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


@dataclass(frozen=True)
class Config:
    db_dsn: str
    courtlistener_token: str | None
    timezone_name: str
    max_runtime_seconds: int
    state_key: str
    log_path: Path
    include_quasi_criminal: bool
    only_courts: tuple[str, ...] | None
    backfill_start_date: date
    page_size: int
    max_pages_per_query: int
    request_timeout_seconds: int
    request_pause_seconds: float
    request_retries: int
    max_court_date_queries: int


class CourtListenerClient:
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
        self._session.headers.update({"User-Agent": "Acquittify-Caselaw-Ingest-Job/1.0"})
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
            params = None
            for record in payload.get("results", []) or []:
                if not isinstance(record, dict):
                    continue
                if (
                    str(record.get("jurisdiction") or "").upper() != "F"
                    or not bool(record.get("in_use", True))
                    or not bool(record.get("has_opinion_scraper", False))
                ):
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
    parser = argparse.ArgumentParser(description="ECS caselaw nightly ingest job")
    parser.add_argument("--db-dsn", default=os.getenv("DATABASE_URL") or os.getenv("ACQ_CASELAW_DB_DSN", ""))
    parser.add_argument("--courtlistener-token", default=os.getenv("COURTLISTENER_API_TOKEN"))
    parser.add_argument("--timezone", default=os.getenv("ACQ_CASELAW_TIMEZONE", DEFAULT_TIMEZONE))
    parser.add_argument(
        "--max-runtime-hours",
        type=float,
        default=float(os.getenv("ACQ_CASELAW_RUNTIME_HOURS", str(DEFAULT_RUNTIME_HOURS))),
    )
    parser.add_argument("--state-key", default=os.getenv("ACQ_CASELAW_STATE_KEY", DEFAULT_STATE_KEY))
    parser.add_argument(
        "--log-path",
        type=Path,
        default=Path(os.getenv("ACQ_CASELAW_LOG_PATH", "/tmp/caselaw_nightly_ingest.jsonl")),
    )
    parser.add_argument("--exclude-quasi", action="store_true")
    parser.add_argument("--only-courts", default=os.getenv("ACQ_CASELAW_ONLY_COURTS", "").strip())
    parser.add_argument(
        "--backfill-start-date",
        default=os.getenv("ACQ_CASELAW_BACKFILL_START_DATE", "2011-01-01").strip(),
    )
    parser.add_argument("--page-size", type=int, default=int(os.getenv("ACQ_CASELAW_PAGE_SIZE", "40")))
    parser.add_argument(
        "--max-pages-per-query",
        type=int,
        default=int(os.getenv("ACQ_CASELAW_MAX_PAGES_PER_QUERY", "20")),
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
    parser.add_argument("--request-retries", type=int, default=int(os.getenv("ACQ_CASELAW_REQUEST_RETRIES", "5")))
    parser.add_argument(
        "--max-court-date-queries",
        type=int,
        default=int(os.getenv("ACQ_CASELAW_MAX_COURT_DATE_QUERIES", "120")),
    )
    return parser.parse_args()


def parse_iso_date(value: str | None) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def normalize_db_dsn(value: str) -> str:
    dsn = str(value or "").strip()
    if not dsn:
        return ""

    # Accept SQLAlchemy URLs from secrets and convert to libpq/psycopg format.
    dsn = re.sub(r"^postgresql\+psycopg2?://", "postgresql://", dsn, flags=re.IGNORECASE)

    # Handle malformed query fragments like '?sslmode' without '=value'.
    dsn = re.sub(r"([?&])sslmode(?=(&|$))", r"\1sslmode=require", dsn, flags=re.IGNORECASE)
    dsn = re.sub(r"([?&])sslmode=(?=(&|$))", r"\1sslmode=require", dsn, flags=re.IGNORECASE)
    return dsn


def to_config(args: argparse.Namespace) -> Config:
    normalized_dsn = normalize_db_dsn(str(args.db_dsn or ""))
    if not normalized_dsn:
        raise SystemExit("Missing --db-dsn (or set DATABASE_URL/ACQ_CASELAW_DB_DSN)")

    only_courts: tuple[str, ...] | None = None
    if args.only_courts:
        parsed = [item.strip().lower() for item in str(args.only_courts).split(",") if item.strip()]
        if parsed:
            only_courts = tuple(parsed)

    backfill_start_date = parse_iso_date(args.backfill_start_date) or date(2011, 1, 1)

    return Config(
        db_dsn=normalized_dsn,
        courtlistener_token=args.courtlistener_token,
        timezone_name=args.timezone,
        max_runtime_seconds=max(60, int(float(args.max_runtime_hours) * 3600)),
        state_key=args.state_key,
        log_path=Path(args.log_path),
        include_quasi_criminal=not bool(args.exclude_quasi),
        only_courts=only_courts,
        backfill_start_date=backfill_start_date,
        page_size=max(1, min(int(args.page_size), 100)),
        max_pages_per_query=max(1, int(args.max_pages_per_query)),
        request_timeout_seconds=max(5, int(args.request_timeout_seconds)),
        request_pause_seconds=max(0.0, float(args.request_pause_seconds)),
        request_retries=max(1, int(args.request_retries)),
        max_court_date_queries=max(1, int(args.max_court_date_queries)),
    )


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


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


def append_log(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def normalize_text(raw: str) -> str:
    text = str(raw or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


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


def classify_case_type(case_name: str, docket_number: str, citations: list[str], opinion_text: str) -> tuple[str, str]:
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

    return "non_criminal", "no criminal indicators matched"


def include_case(case_type: str, include_quasi_criminal: bool) -> bool:
    if case_type == "criminal":
        return True
    if case_type == "quasi_criminal":
        return include_quasi_criminal
    return False


def infer_court_level(court_id: str, court_name: str) -> str:
    cid = str(court_id or "").lower()
    cname = str(court_name or "").lower()
    if cid == "scotus" or "supreme" in cname:
        return "supreme"
    if cid.startswith("ca") or "appeal" in cname or "circuit" in cname:
        return "appeals"
    if "district" in cname:
        return "district"
    return "other"


def opinion_text_from_detail(payload: dict[str, Any] | None) -> str:
    if not payload:
        return ""
    for key in ("plain_text", "html_with_citations", "html", "opinion_text"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def opinion_text_from_search_item(item: dict[str, Any]) -> str:
    snippets: list[str] = []
    top_snippet = item.get("snippet")
    if isinstance(top_snippet, str) and top_snippet.strip():
        snippets.append(top_snippet)
    for entry in item.get("opinions", []) or []:
        if not isinstance(entry, dict):
            continue
        value = entry.get("snippet")
        if isinstance(value, str) and value.strip():
            snippets.append(value)
        if len(snippets) >= 4:
            break
    return "\n\n".join(snippets)


def frontmatter_to_yaml(frontmatter: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in frontmatter.items():
        lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines)


def compact_text(value: str, limit: int) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    if len(text) <= max(1, limit):
        return text
    clipped = text[: max(1, limit)].rsplit(" ", 1)[0].strip()
    return clipped or text[: max(1, limit)].strip()


def first_sentence(value: str, limit: int) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)
    candidate = parts[0] if parts else text
    return compact_text(candidate, limit)


def build_case_summary_and_holding(case_name: str, opinion_text: str) -> tuple[str, str]:
    summary = first_sentence(opinion_text, 680) or compact_text(opinion_text, 680) or case_name
    holding = first_sentence(opinion_text, 420) or compact_text(opinion_text, 420)
    if not holding:
        holding = compact_text(summary, 420)
    return summary, holding


def case_frontmatter(*, case_id: str, case_name: str, court_id: str, court_name: str, date_filed: str, citations: list[str],
                     case_type: str, reason: str, cluster_id: int, opinion_id: int | None, absolute_url: str,
                     taxonomy_codes: list[str], taxonomy_version: str, case_summary: str,
                     essential_holding: str) -> dict[str, Any]:
    unique_citations = [entry for entry in citations if str(entry or "").strip()]
    primary_citation = unique_citations[0] if unique_citations else ""
    return {
        "type": "case",
        "case_id": case_id,
        "title": case_name,
        "court": court_name,
        "court_level": infer_court_level(court_id, court_name),
        "jurisdiction": "US",
        "date_decided": date_filed,
        "publication_status": "published",
        "opinion_type": "majority",
        "judges": {"author": "", "joining": []},
        "citations_in_text": unique_citations,
        "case_summary": case_summary,
        "essential_holding": essential_holding,
        "case_type": case_type,
        "case_type_reason": reason,
        "case_taxonomies": [{"code": code, "label": code} for code in taxonomy_codes],
        "sources": {
            "source": "courtlistener",
            "courtlistener_cluster_id": cluster_id,
            "courtlistener_opinion_id": opinion_id,
            "opinion_url": absolute_url,
            "primary_citation": primary_citation,
        },
        "taxonomy_version": taxonomy_version,
    }


def synthetic_unit_id(case_id: str, code: str, version: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"acquittify:caselaw:{case_id}:{code}:{version}")


class CaseStore:
    @staticmethod
    def init_schema(conn) -> None:
        with conn.cursor() as cur:
            cur.execute("CREATE SCHEMA IF NOT EXISTS derived;")
            cur.execute(
                """
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
                """
            )
            cur.execute(
                """
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
                """
            )
            cur.execute(
                """
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
                    UNIQUE (code, version)
                );
                """
            )
            # Backward-compatible upgrades for preexisting taxonomy_node tables.
            cur.execute(
                """
                ALTER TABLE derived.taxonomy_node
                    ADD COLUMN IF NOT EXISTS synonyms JSONB NOT NULL DEFAULT '[]'::jsonb,
                    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'ACTIVE',
                    ADD COLUMN IF NOT EXISTS deprecated_at TIMESTAMPTZ NULL,
                    ADD COLUMN IF NOT EXISTS replaced_by_code TEXT NULL,
                    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
                """
            )
            cur.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS ux_derived_taxonomy_node_code_version
                ON derived.taxonomy_node (code, version);
                """
            )
            cur.execute(
                """
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
                """
            )
        conn.commit()

    @staticmethod
    def ensure_default_taxonomy(conn, version: str = "2026.01") -> None:
        nodes = [
            ("CASELAW.GENERAL", "General Caselaw", None),
            ("CRIM.PROC.GENERAL", "Criminal Procedure", "CASELAW.GENERAL"),
            ("APPEAL.STANDARD.GENERAL", "Appeal Standards", "CASELAW.GENERAL"),
        ]
        with conn.cursor() as cur:
            for code, label, parent in nodes:
                cur.execute(
                    """
                    INSERT INTO derived.taxonomy_node (code, version, label, parent_code, synonyms, status)
                    VALUES (%s, %s, %s, %s, '[]'::jsonb, 'ACTIVE')
                    ON CONFLICT (code, version) DO NOTHING
                    """,
                    (code, version, label, parent),
                )
        conn.commit()

    @staticmethod
    def load_state(conn, state_key: str, default_date: date) -> tuple[date, int]:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT backfill_cursor_date, backfill_court_index
                FROM derived.caselaw_nightly_state
                WHERE state_key = %s
                """,
                (state_key,),
            )
            row = cur.fetchone()
            if row:
                return row["backfill_cursor_date"], int(row.get("backfill_court_index") or 0)
            cur.execute(
                """
                INSERT INTO derived.caselaw_nightly_state (
                    state_key,
                    backfill_cursor_date,
                    backfill_court_index,
                    updated_at
                ) VALUES (%s, %s, 0, NOW())
                ON CONFLICT (state_key) DO NOTHING
                """,
                (state_key, default_date),
            )
        conn.commit()
        return default_date, 0

    @staticmethod
    def save_state(conn, state_key: str, cursor_date: date, court_index: int, status: str, summary: dict[str, Any]) -> None:
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
                ) VALUES (%s, %s, %s, NOW(), NOW(), %s, CAST(%s AS jsonb), NOW())
                ON CONFLICT (state_key)
                DO UPDATE SET
                    backfill_cursor_date = EXCLUDED.backfill_cursor_date,
                    backfill_court_index = EXCLUDED.backfill_court_index,
                    last_run_finished_at = EXCLUDED.last_run_finished_at,
                    last_run_status = EXCLUDED.last_run_status,
                    last_run_summary = EXCLUDED.last_run_summary,
                    updated_at = NOW()
                """,
                (state_key, cursor_date, court_index, status, json.dumps(summary)),
            )
        conn.commit()

    @staticmethod
    def insert_case(conn, payload: dict[str, Any]) -> bool:
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
                    %s::text[], %s, %s, CAST(%s AS jsonb), %s, %s, CAST(%s AS jsonb), NOW(), NOW()
                )
                ON CONFLICT (courtlistener_cluster_id) DO NOTHING
                RETURNING id
                """,
                (
                    payload["case_id"],
                    payload["courtlistener_cluster_id"],
                    payload.get("courtlistener_opinion_id"),
                    payload["court_id"],
                    payload["court_name"],
                    payload.get("date_filed"),
                    payload.get("docket_number"),
                    payload["case_name"],
                    payload["case_type"],
                    payload.get("taxonomy_codes") or [],
                    payload["taxonomy_version"],
                    payload["frontmatter_yaml"],
                    json.dumps(payload["frontmatter_json"], ensure_ascii=False),
                    payload.get("opinion_text", ""),
                    payload.get("opinion_text_sha256", ""),
                    json.dumps(payload.get("source_payload") or {}, ensure_ascii=False),
                ),
            )
            inserted = cur.fetchone() is not None
        conn.commit()
        return inserted

    @staticmethod
    def insert_legal_units(conn, *, payload: dict[str, Any], ingestion_batch_id: str) -> int:
        case_id = payload["case_id"]
        taxonomy_codes = list(payload.get("taxonomy_codes") or [])
        if not taxonomy_codes:
            return 0
        date_text = str(payload.get("date_filed") or "")
        year = 1900
        if len(date_text) >= 4 and date_text[:4].isdigit():
            year = int(date_text[:4])
        inserted = 0
        with conn.cursor() as cur:
            for code in taxonomy_codes:
                unit_id = synthetic_unit_id(case_id, code, payload["taxonomy_version"])
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
                        authority_weight,
                        favorability,
                        secondary_taxonomy_ids,
                        standard_unit_ids,
                        unit_text,
                        source_opinion_id,
                        ingestion_batch_id
                    ) VALUES (
                        %s, 'holding', %s, %s, %s, %s, %s,
                        'direct', 'unknown', 'unknown', TRUE, FALSE,
                        100, 0, '{}'::text[], '{}'::uuid[], %s, %s, %s
                    )
                    ON CONFLICT (unit_id) DO NOTHING
                    RETURNING id
                    """,
                    (
                        unit_id,
                        code,
                        payload["taxonomy_version"],
                        payload["court_id"],
                        infer_court_level(payload["court_id"], payload["court_name"]),
                        year,
                        payload["case_name"],
                        int(payload["courtlistener_cluster_id"]),
                        ingestion_batch_id,
                    ),
                )
                if cur.fetchone() is not None:
                    inserted += 1
        conn.commit()
        return inserted


def to_absolute_courtlistener_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    if raw.startswith("/"):
        return f"https://www.courtlistener.com{raw}"
    return f"https://www.courtlistener.com/{raw}"


def taxonomy_codes_for(case_type: str) -> list[str]:
    if case_type in {"criminal", "quasi_criminal"}:
        return ["CRIM.PROC.GENERAL", "CASELAW.GENERAL"]
    return ["APPEAL.STANDARD.GENERAL", "CASELAW.GENERAL"]


def run(config: Config) -> dict[str, Any]:
    started_at = utc_now()
    tz = ZoneInfo(config.timezone_name)
    today_local = datetime.now(tz).date()

    ingestion_batch_id = f"ecs_caselaw_nightly:{started_at.strftime('%Y%m%dT%H%M%SZ')}"

    summary: dict[str, Any] = {
        "event": "ecs_caselaw_nightly_summary",
        "started_at": started_at.isoformat(),
        "finished_at": None,
        "status": "ok",
        "timezone": config.timezone_name,
        "today_local": today_local.isoformat(),
        "backfill_start_date": config.backfill_start_date.isoformat(),
        "ingestion_batch_id": ingestion_batch_id,
        "scanned": 0,
        "inserted": 0,
        "ontology_units_inserted": 0,
        "skipped_non_criminal": 0,
        "errors": 0,
        "steps": [],
    }

    try:
        with psycopg.connect(config.db_dsn) as conn:
            CaseStore.init_schema(conn)
            CaseStore.ensure_default_taxonomy(conn, version="2026.01")

            client = CourtListenerClient(
                token=config.courtlistener_token,
                timeout_seconds=config.request_timeout_seconds,
                pause_seconds=config.request_pause_seconds,
                retries=config.request_retries,
            )

            if config.only_courts:
                ordered_courts = list(config.only_courts)
            else:
                ordered_courts = order_federal_courts(client.iter_federal_court_ids())

            cursor_date, court_index = CaseStore.load_state(
                conn,
                config.state_key,
                default_date=today_local,
            )

            deadline = time.monotonic() + config.max_runtime_seconds
            steps_used = 0

            # Always process today's priority courts first to keep current ingest fresh.
            priority_run = [court for court in PRIORITY_COURTS if court in ordered_courts]
            for court_id in priority_run:
                if steps_used >= config.max_court_date_queries or time.monotonic() >= deadline:
                    break
                step = process_court_date(
                    conn=conn,
                    client=client,
                    court_id=court_id,
                    target_date=today_local,
                    config=config,
                    ingestion_batch_id=ingestion_batch_id,
                )
                steps_used += 1
                apply_step_summary(summary, step)
                summary["steps"].append(step)

            # Backfill cursor sweep across courts/dates.
            while steps_used < config.max_court_date_queries and time.monotonic() < deadline:
                if cursor_date < config.backfill_start_date:
                    summary["status"] = "backfill_complete"
                    break
                if not ordered_courts:
                    break

                if court_index >= len(ordered_courts):
                    court_index = 0
                    cursor_date -= timedelta(days=1)
                    continue

                court_id = ordered_courts[court_index]
                step = process_court_date(
                    conn=conn,
                    client=client,
                    court_id=court_id,
                    target_date=cursor_date,
                    config=config,
                    ingestion_batch_id=ingestion_batch_id,
                )
                steps_used += 1
                apply_step_summary(summary, step)
                summary["steps"].append(step)

                court_index += 1
                if court_index >= len(ordered_courts):
                    court_index = 0
                    cursor_date -= timedelta(days=1)

            summary["backfill_cursor_date"] = cursor_date.isoformat()
            summary["backfill_court_index"] = court_index
            summary["ordered_courts"] = ordered_courts
            summary["step_count"] = steps_used

            if time.monotonic() >= deadline and summary["status"] == "ok":
                summary["status"] = "runtime_exhausted"
            elif steps_used >= config.max_court_date_queries and summary["status"] == "ok":
                summary["status"] = "max_queries_reached"

            CaseStore.save_state(
                conn,
                config.state_key,
                cursor_date,
                court_index,
                summary["status"],
                summary,
            )

    except Exception as exc:  # noqa: BLE001
        summary["status"] = "error"
        summary["errors"] = int(summary.get("errors", 0)) + 1
        summary["error"] = str(exc)

    finally:
        summary["finished_at"] = utc_now().isoformat()
        append_log(config.log_path, summary)

    return summary


def apply_step_summary(summary: dict[str, Any], step: dict[str, Any]) -> None:
    summary["scanned"] = int(summary.get("scanned", 0)) + int(step.get("scanned", 0))
    summary["inserted"] = int(summary.get("inserted", 0)) + int(step.get("inserted", 0))
    summary["ontology_units_inserted"] = int(summary.get("ontology_units_inserted", 0)) + int(
        step.get("ontology_units_inserted", 0)
    )
    summary["skipped_non_criminal"] = int(summary.get("skipped_non_criminal", 0)) + int(
        step.get("skipped_non_criminal", 0)
    )
    summary["errors"] = int(summary.get("errors", 0)) + int(step.get("errors", 0))


def process_court_date(
    *,
    conn,
    client: CourtListenerClient,
    court_id: str,
    target_date: date,
    config: Config,
    ingestion_batch_id: str,
) -> dict[str, Any]:
    step = {
        "court_id": court_id,
        "date": target_date.isoformat(),
        "scanned": 0,
        "inserted": 0,
        "ontology_units_inserted": 0,
        "skipped_non_criminal": 0,
        "errors": 0,
        "error_samples": [],
    }

    try:
        for item in client.iter_daily_results(
            court_id=court_id,
            target_date=target_date,
            page_size=config.page_size,
            max_pages=config.max_pages_per_query,
        ):
            try:
                step["scanned"] += 1

                cluster_id = int(item.get("cluster_id") or 0)
                if not cluster_id:
                    continue
                case_id = f"case.courtlistener.cluster.{cluster_id}"
                case_name = str(item.get("caseName") or item.get("case_name") or "").strip() or case_id
                court_name = str(item.get("court") or court_id).strip() or court_id
                date_filed = str(item.get("dateFiled") or target_date.isoformat()).strip()
                docket_number = str(item.get("docketNumber") or "").strip()
                citations = extract_citations(item)

                opinions = item.get("opinions") or []
                opinion_id = None
                if isinstance(opinions, list) and opinions:
                    first = opinions[0]
                    if isinstance(first, dict):
                        opinion_id = first.get("id")

                detail = client.fetch_opinion_detail(int(opinion_id)) if opinion_id else None
                opinion_text = normalize_text(opinion_text_from_detail(detail) or opinion_text_from_search_item(item))
                case_type, reason = classify_case_type(case_name, docket_number, citations, opinion_text)
                if not include_case(case_type, config.include_quasi_criminal):
                    step["skipped_non_criminal"] += 1
                    continue

                taxonomy_codes = taxonomy_codes_for(case_type)
                absolute_url = to_absolute_courtlistener_url(str(item.get("absolute_url") or ""))
                case_summary, essential_holding = build_case_summary_and_holding(case_name, opinion_text)
                fm = case_frontmatter(
                    case_id=case_id,
                    case_name=case_name,
                    court_id=court_id,
                    court_name=court_name,
                    date_filed=date_filed,
                    citations=citations,
                    case_type=case_type,
                    reason=reason,
                    cluster_id=cluster_id,
                    opinion_id=int(opinion_id) if opinion_id else None,
                    absolute_url=absolute_url,
                    taxonomy_codes=taxonomy_codes,
                    taxonomy_version="2026.01",
                    case_summary=case_summary,
                    essential_holding=essential_holding,
                )
                payload = {
                    "case_id": case_id,
                    "courtlistener_cluster_id": cluster_id,
                    "courtlistener_opinion_id": int(opinion_id) if opinion_id else None,
                    "court_id": court_id,
                    "court_name": court_name,
                    "date_filed": date_filed if parse_iso_date(date_filed) else None,
                    "docket_number": docket_number,
                    "case_name": case_name,
                    "case_type": case_type,
                    "taxonomy_codes": taxonomy_codes,
                    "taxonomy_version": "2026.01",
                    "frontmatter_yaml": frontmatter_to_yaml(fm),
                    "frontmatter_json": fm,
                    "opinion_text": opinion_text,
                    "opinion_text_sha256": hashlib.sha256(opinion_text.encode("utf-8")).hexdigest() if opinion_text else "",
                    "source_payload": item,
                }

                inserted = CaseStore.insert_case(conn, payload)
                if inserted:
                    step["inserted"] += 1
                    step["ontology_units_inserted"] += CaseStore.insert_legal_units(
                        conn,
                        payload=payload,
                        ingestion_batch_id=ingestion_batch_id,
                    )
            except Exception as exc:  # noqa: BLE001
                try:
                    conn.rollback()
                except Exception:  # noqa: BLE001
                    pass
                step["errors"] += 1
                samples = step.get("error_samples") or []
                if len(samples) < 5:
                    samples.append(str(exc)[:300])
                    step["error_samples"] = samples

    except Exception as exc:  # noqa: BLE001
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        step["errors"] += 1
        samples = step.get("error_samples") or []
        if len(samples) < 5:
            samples.append(str(exc)[:300])
            step["error_samples"] = samples

    return step


def main() -> int:
    args = parse_args()
    config = to_config(args)
    summary = run(config)
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary.get("status") != "error" else 1


if __name__ == "__main__":
    raise SystemExit(main())
