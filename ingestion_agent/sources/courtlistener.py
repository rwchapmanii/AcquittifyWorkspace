"""CourtListener REST API client."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, Optional
import hashlib
import json
import random
import time
import requests

from ingestion_agent.config import Settings

TEXT_FIELDS = ("plain_text", "html_with_citations", "html", "opinion_text")


class CourtListenerClient:
    """Simple REST client for CourtListener opinions and RECAP documents."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._last_opinion_fetch_at: float | None = None

    def _headers(self) -> Dict[str, str]:
        headers = {"User-Agent": self.settings.user_agent}
        if self.settings.api_token:
            headers["Authorization"] = f"Token {self.settings.api_token}"
        return headers

    def _get(self, path: str, params: Dict[str, str]) -> Dict:
        url = f"{self.settings.courtlistener_base_url}{path}"
        response = requests.get(url, headers=self._headers(), params=params, timeout=60)
        response.raise_for_status()
        return response.json()

    def _cache_root(self) -> Path:
        path = Path(self.settings.cache_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def cache_path_for_opinion(self, opinion_id: str) -> Path:
        return self._cache_root() / f"opinion_{opinion_id}.json"

    def _extract_text(self, record: Dict) -> str:
        for key in TEXT_FIELDS:
            value = record.get(key)
            if value:
                return value
        return ""

    def opinion_text_hash(self, record: Dict) -> str:
        text = self._extract_text(record)
        if not text:
            return ""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _sleep_between_opinion_fetches(self) -> None:
        min_ms = max(0, self.settings.opinion_fetch_min_delay_ms)
        max_ms = max(min_ms, self.settings.opinion_fetch_max_delay_ms)
        delay = random.uniform(min_ms, max_ms) / 1000.0
        time.sleep(delay)

    def iter_opinion_ids(self, since: Optional[str], max_pages: int) -> Iterator[str]:
        """Yield opinion IDs from the API list endpoint."""
        params = {"page": "1", "page_size": "100"}
        if since:
            params["date_filed__gte"] = since
        page = 1
        while page <= max_pages:
            params["page"] = str(page)
            payload = self._get(self.settings.opinions_endpoint, params)
            for item in payload.get("results", []):
                opinion_id = item.get("id")
                if opinion_id is not None:
                    yield str(opinion_id)
            if not payload.get("next"):
                break
            page += 1

    def fetch_opinion(self, opinion_id: str) -> Dict:
        """Fetch a single opinion record by ID, using on-disk cache when available."""
        cache_path = self.cache_path_for_opinion(opinion_id)
        if self.settings.cache_enabled and cache_path.exists():
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                payload = cached.get("payload")
                if isinstance(payload, dict):
                    return payload
            except Exception:
                pass

        path = f"{self.settings.opinions_endpoint.rstrip('/')}/{opinion_id}/"
        payload = self._get(path, {})
        if self.settings.cache_enabled:
            record = {
                "id": opinion_id,
                "fetched_at": datetime.utcnow().isoformat(),
                "text_hash": self.opinion_text_hash(payload),
                "payload": payload,
            }
            cache_path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        self._sleep_between_opinion_fetches()
        return payload

    def iter_opinions(self, since: Optional[str], max_pages: int) -> Iterator[Dict]:
        """Yield opinion records from the API, fetching by ID with caching."""
        for opinion_id in self.iter_opinion_ids(since=since, max_pages=max_pages):
            yield self.fetch_opinion(opinion_id)

    def iter_recap_filings(self, since: Optional[str], max_pages: int) -> Iterator[Dict]:
        """Yield RECAP document records from the API."""
        params = {"page": "1", "page_size": "100"}
        if since:
            params["date_filed__gte"] = since
        page = 1
        while page <= max_pages:
            params["page"] = str(page)
            payload = self._get(self.settings.recap_endpoint, params)
            for item in payload.get("results", []):
                yield item
            if not payload.get("next"):
                break
            page += 1
