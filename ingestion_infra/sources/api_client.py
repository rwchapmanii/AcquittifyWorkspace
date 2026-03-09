"""CourtListener REST API client."""

from __future__ import annotations

from typing import Dict, Iterator, Tuple
import logging
import requests

from ingestion_infra.config import Settings

LOGGER = logging.getLogger(__name__)

ENDPOINTS = {
    "courts": "/courts/",
    "dockets": "/dockets/",
    "opinion-clusters": "/opinion-clusters/",
    "opinions": "/opinions/",
}


class CourtListenerAPI:
    """Simple REST client for CourtListener."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _headers(self) -> Dict[str, str]:
        headers = {"User-Agent": "CourtListener-Ingestion/1.0"}
        if self.settings.api_token:
            headers["Authorization"] = f"Token {self.settings.api_token}"
        return headers

    def _get(self, path: str, params: Dict[str, str]) -> Dict:
        url = f"{self.settings.api_base_url}{path}"
        response = requests.get(url, headers=self._headers(), params=params, timeout=60)
        response.raise_for_status()
        return response.json()

    def iter_entities(
        self,
        entity: str,
        since: str | None,
        start_page: int = 1,
    ) -> Iterator[Tuple[int, Dict]]:
        """Iterate entities with pagination and optional date filter."""
        if entity not in ENDPOINTS:
            raise ValueError(f"Unsupported entity: {entity}")
        params = {"page": str(start_page), "page_size": str(self.settings.api_page_size)}
        if since:
            params["date_filed__gte"] = since
        page = start_page
        while True:
            params["page"] = str(page)
            payload = self._get(ENDPOINTS[entity], params)
            for item in payload.get("results", []):
                yield page, item
            if not payload.get("next"):
                break
            page += 1

    def get_record_id(self, entity: str, record: Dict) -> str | None:
        """Extract stable record id from API record."""
        record_id = record.get("id")
        if record_id is None:
            LOGGER.warning("Missing id for %s record", entity)
            return None
        return str(record_id)
