"""Configuration for ingestion infrastructure."""

from dataclasses import dataclass
import json
import os
from typing import Dict, List


@dataclass(frozen=True)
class Settings:
    """Runtime settings pulled from environment variables."""

    api_base_url: str = os.getenv("COURTLISTENER_API_BASE_URL", "https://www.courtlistener.com/api/rest/v3")
    api_token: str | None = os.getenv("COURTLISTENER_API_TOKEN")
    api_page_size: int = int(os.getenv("COURTLISTENER_API_PAGE_SIZE", "100"))

    s3_bucket: str = os.getenv("COURTLISTENER_S3_BUCKET", "courtlistener")
    s3_prefix: str = os.getenv("COURTLISTENER_S3_PREFIX", "bulk-data")
    s3_region: str | None = os.getenv("COURTLISTENER_S3_REGION")
    s3_endpoint_url: str | None = os.getenv("COURTLISTENER_S3_ENDPOINT_URL")
    s3_unsigned: bool = os.getenv("COURTLISTENER_S3_UNSIGNED", "true").lower() == "true"
    s3_addressing_style: str = os.getenv("COURTLISTENER_S3_ADDRESSING_STYLE", "auto")
    s3_http_fallback_url: str | None = os.getenv("COURTLISTENER_S3_HTTP_FALLBACK_URL")
    s3_stream_max_retries: int = int(os.getenv("COURTLISTENER_S3_STREAM_MAX_RETRIES", "15"))
    s3_stream_retry_backoff: float = float(os.getenv("COURTLISTENER_S3_STREAM_RETRY_BACKOFF", "5"))

    bulk_data_url: str = os.getenv("COURTLISTENER_BULK_DATA_URL", "https://www.courtlistener.com/api/bulk-data/")

    db_dsn: str = os.getenv(
        "COURTLISTENER_DB_DSN",
        "postgresql://acquittify:acquittify@localhost:5432/courtlistener",
    )

    state_path: str = os.getenv("COURTLISTENER_STATE_PATH", "ingestion_state.json")
    log_level: str = os.getenv("COURTLISTENER_LOG_LEVEL", "INFO")
    checkpoint_every: int = int(os.getenv("COURTLISTENER_CHECKPOINT_EVERY", "1000"))

    # Optional explicit mapping of entity -> list of S3 keys.
    bulk_keys_json: str | None = os.getenv("COURTLISTENER_BULK_KEYS_JSON")

    def bulk_keys(self) -> Dict[str, List[str]]:
        if not self.bulk_keys_json:
            return {}
        return json.loads(self.bulk_keys_json)
