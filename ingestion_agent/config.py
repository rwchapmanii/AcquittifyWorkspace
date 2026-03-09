"""Configuration defaults for the ingestion agent."""

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    """Runtime settings for the ingestion pipeline."""

    courtlistener_base_url: str = "https://www.courtlistener.com/api/rest/v3"
    search_endpoint: str = "/search/"
    opinions_endpoint: str = "/opinions/"
    recap_endpoint: str = "/recap-documents/"
    api_token: str | None = os.getenv("COURTLISTENER_API_TOKEN")
    user_agent: str = "Acquittify-Ingestion/1.0"

    opinion_fetch_min_delay_ms: int = int(os.getenv("COURTLISTENER_OPINION_FETCH_MIN_DELAY_MS", "200"))
    opinion_fetch_max_delay_ms: int = int(os.getenv("COURTLISTENER_OPINION_FETCH_MAX_DELAY_MS", "500"))
    cache_dir: str = os.getenv("COURTLISTENER_CACHE_DIR", "ingestion_agent/data/cache")
    cache_enabled: bool = os.getenv("COURTLISTENER_CACHE_ENABLED", "true").lower() == "true"

    output_path: str = "ingestion_agent/output/chunks.jsonl"
    state_path: str = "ingestion_agent/data/state.json"

    max_chars_per_chunk: int = 2000
    min_chars_per_chunk: int = 400
    overlap_paragraphs: int = 1
