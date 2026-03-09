import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

os.environ.setdefault("AUTH_SECRET_KEY", "test-secret-key")
os.environ.setdefault("AUTH_PASSWORD_RESET_DEV_RETURN_TOKEN", "true")
os.environ.setdefault("AUTH_PASSWORD_MIN_LENGTH", "8")
os.environ.setdefault("AUTH_PASSWORD_REQUIRE_UPPER", "false")
os.environ.setdefault("AUTH_PASSWORD_REQUIRE_LOWER", "true")
os.environ.setdefault("AUTH_PASSWORD_REQUIRE_NUMBER", "false")
os.environ.setdefault("AUTH_PASSWORD_REQUIRE_SYMBOL", "false")
os.environ.setdefault("AUTH_RATE_LIMIT_ENABLED", "true")
os.environ.setdefault("AUTH_RATE_LIMIT_MAX_ATTEMPTS", "10")
os.environ.setdefault("AUTH_RATE_LIMIT_WINDOW_SECONDS", "60")
os.environ.setdefault("AUTH_RATE_LIMIT_BACKEND", "memory")
os.environ.setdefault("AUTH_COOKIE_SECURE", "false")

from app.core.config import get_settings

get_settings.cache_clear()

from app.main import app
import app.main as app_main


def _truncate_public_tables(engine: Engine) -> None:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public' AND tablename <> 'alembic_version'
                """
            )
        ).fetchall()
        table_names = [row[0] for row in rows]
        if not table_names:
            return
        joined = ", ".join(f'"{name}"' for name in table_names)
        conn.execute(text(f"TRUNCATE TABLE {joined} RESTART IDENTITY CASCADE"))


@pytest.fixture(scope="session")
def engine() -> Generator[Engine, None, None]:
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL must be set for integration tests")
    engine = create_engine(settings.database_url, future=True)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def isolate_test_data(engine: Engine) -> Generator[None, None, None]:
    _truncate_public_tables(engine)
    limiter = getattr(app_main, "auth_rate_limiter", None)
    if limiter is not None and hasattr(limiter, "reset"):
        limiter.reset()

    yield

    _truncate_public_tables(engine)
    if limiter is not None and hasattr(limiter, "reset"):
        limiter.reset()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_session(engine: Engine) -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
