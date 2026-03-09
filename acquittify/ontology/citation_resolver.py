from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any
from urllib.parse import urlparse

import requests

from acquittify.metadata_extract import normalize_citation


@dataclass(frozen=True)
class ResolvedCitation:
    query_citation: str
    normalized_citation: str
    resolved_case_id: str | None
    canonical_citation: str | None
    confidence: float
    source: str
    raw_payload: dict[str, Any] | list[Any] | None = None


class CitationResolver:
    def __init__(
        self,
        lookup_url: str,
        api_token: str | None = None,
        cache_path: Path | None = None,
        request_timeout: int = 20,
        session: requests.Session | None = None,
    ) -> None:
        self.lookup_url = (lookup_url or "").strip()
        self.api_token = api_token
        self.cache_path = cache_path
        self.request_timeout = request_timeout
        self.session = session or requests.Session()

        if self.cache_path:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._init_cache()

    def _db(self) -> sqlite3.Connection:
        if not self.cache_path:
            raise RuntimeError("cache_path not configured")
        return sqlite3.connect(self.cache_path)

    def _init_cache(self) -> None:
        with self._db() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS citation_resolution_cache (
                    normalized_citation TEXT PRIMARY KEY,
                    query_citation TEXT NOT NULL,
                    resolved_case_id TEXT,
                    canonical_citation TEXT,
                    confidence REAL NOT NULL,
                    source TEXT NOT NULL,
                    raw_payload TEXT,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": "Acquittify-Ontology/1.0"}
        if self.api_token:
            headers["Authorization"] = f"Token {self.api_token}"
        return headers

    def _read_cache(self, normalized_citation: str) -> ResolvedCitation | None:
        if not self.cache_path:
            return None
        with self._db() as conn:
            row = conn.execute(
                """
                SELECT query_citation, normalized_citation, resolved_case_id,
                       canonical_citation, confidence, source, raw_payload
                FROM citation_resolution_cache
                WHERE normalized_citation = ?
                """,
                (normalized_citation,),
            ).fetchone()

        if not row:
            return None

        raw_payload = None
        if row[6]:
            try:
                raw_payload = json.loads(row[6])
            except Exception:
                raw_payload = None

        return ResolvedCitation(
            query_citation=row[0],
            normalized_citation=row[1],
            resolved_case_id=row[2],
            canonical_citation=row[3],
            confidence=float(row[4]),
            source=row[5],
            raw_payload=raw_payload,
        )

    def _write_cache(self, result: ResolvedCitation) -> None:
        if not self.cache_path:
            return
        payload_json = json.dumps(result.raw_payload, ensure_ascii=False) if result.raw_payload is not None else None
        with self._db() as conn:
            conn.execute(
                """
                INSERT INTO citation_resolution_cache (
                    normalized_citation,
                    query_citation,
                    resolved_case_id,
                    canonical_citation,
                    confidence,
                    source,
                    raw_payload,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(normalized_citation)
                DO UPDATE SET
                    query_citation = excluded.query_citation,
                    resolved_case_id = excluded.resolved_case_id,
                    canonical_citation = excluded.canonical_citation,
                    confidence = excluded.confidence,
                    source = excluded.source,
                    raw_payload = excluded.raw_payload,
                    updated_at = excluded.updated_at
                """,
                (
                    result.normalized_citation,
                    result.query_citation,
                    result.resolved_case_id,
                    result.canonical_citation,
                    result.confidence,
                    result.source,
                    payload_json,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def resolve_many(self, citations: list[str]) -> list[ResolvedCitation]:
        return [self.resolve(citation) for citation in citations]

    def resolve(self, citation: str) -> ResolvedCitation:
        normalized = normalize_citation(citation)
        if not normalized:
            return ResolvedCitation(
                query_citation=citation,
                normalized_citation="",
                resolved_case_id=None,
                canonical_citation=None,
                confidence=0.0,
                source="empty-citation",
                raw_payload=None,
            )

        cached = self._read_cache(normalized)
        if cached is not None:
            return cached

        result = self._resolve_remote(citation, normalized)
        self._write_cache(result)
        return result

    def _resolve_remote(self, citation: str, normalized: str) -> ResolvedCitation:
        if not self.lookup_url:
            return ResolvedCitation(
                query_citation=citation,
                normalized_citation=normalized,
                resolved_case_id=None,
                canonical_citation=None,
                confidence=0.0,
                source="resolver-disabled",
                raw_payload=None,
            )

        payload: dict[str, Any] | list[Any] | None = None
        for params in ({"q": normalized}, {"citation": normalized}, {"text": normalized}):
            try:
                response = self.session.get(
                    self.lookup_url,
                    headers=self._headers(),
                    params=params,
                    timeout=self.request_timeout,
                )
            except requests.RequestException:
                continue
            if response.status_code >= 400:
                continue
            try:
                payload = response.json()
            except ValueError:
                payload = None
            if payload is not None:
                break

        resolved_case_id, canonical_citation, confidence = self._parse_payload(payload)
        source = "courtlistener-api" if payload is not None else "courtlistener-api-error"
        return ResolvedCitation(
            query_citation=citation,
            normalized_citation=normalized,
            resolved_case_id=resolved_case_id,
            canonical_citation=canonical_citation,
            confidence=confidence,
            source=source,
            raw_payload=payload,
        )

    @staticmethod
    def _extract_candidates(payload: dict[str, Any] | list[Any] | None) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []

        candidates: list[dict[str, Any]] = []
        for key in ("results", "matches", "clusters", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                candidates.extend(item for item in value if isinstance(item, dict))

        if not candidates:
            candidates = [payload]
        return candidates

    @staticmethod
    def _candidate_confidence(candidate: dict[str, Any]) -> float:
        for key in ("confidence", "score", "match_score"):
            raw = candidate.get(key)
            if isinstance(raw, (int, float)):
                value = float(raw)
                if value > 1.0 and value <= 100.0:
                    value = value / 100.0
                if value < 0.0:
                    value = 0.0
                if value > 1.0:
                    value = 1.0
                return value
        return 1.0 if CitationResolver._candidate_case_id(candidate) else 0.0

    @staticmethod
    def _candidate_case_id(candidate: dict[str, Any]) -> str | None:
        for key in ("case_id", "cluster_id", "cluster", "id", "opinion_id"):
            value = candidate.get(key)
            if value is not None and str(value).strip():
                return f"courtlistener.{str(value).strip()}"

        for key in ("absolute_url", "resource_uri", "url"):
            value = candidate.get(key)
            if isinstance(value, str) and value.strip():
                parsed = urlparse(value)
                parts = [p for p in parsed.path.split("/") if p]
                for part in reversed(parts):
                    if part.isdigit():
                        return f"courtlistener.{part}"
        return None

    @staticmethod
    def _candidate_citation(candidate: dict[str, Any]) -> str | None:
        for key in ("citation", "cite", "normalized_citation", "matched_citation"):
            value = candidate.get(key)
            if isinstance(value, str) and value.strip():
                return normalize_citation(value)
        return None

    def _parse_payload(self, payload: dict[str, Any] | list[Any] | None) -> tuple[str | None, str | None, float]:
        candidates = self._extract_candidates(payload)
        if not candidates:
            return None, None, 0.0

        best = max(candidates, key=self._candidate_confidence)
        resolved_case_id = self._candidate_case_id(best)
        canonical_citation = self._candidate_citation(best)
        confidence = self._candidate_confidence(best)
        return resolved_case_id, canonical_citation, confidence
