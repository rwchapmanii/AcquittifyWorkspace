from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from celery import Celery

from app.core.config import get_settings


def _normalize_redis_url(url: str) -> str:
    if not url.startswith("rediss://"):
        return url

    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.setdefault("ssl_cert_reqs", "CERT_REQUIRED")
    return urlunparse(parsed._replace(query=urlencode(query)))


settings = get_settings()
broker_url = _normalize_redis_url(settings.redis_url or "redis://localhost:6379/0")

celery_app = Celery(
    "peregrine",
    broker=broker_url,
    backend=broker_url,
)

celery_app.conf.task_track_started = True
celery_app.conf.result_expires = 3600

# Ensure tasks are registered with the Celery app
import app.workers.tasks  # noqa: F401
