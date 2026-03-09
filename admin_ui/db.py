import os
from contextlib import contextmanager
from typing import Iterator, Optional

import psycopg


READ_DSN_ENV = "ACQUITTIFY_DB_DSN_READONLY"
WRITE_DSN_ENV = "ACQUITTIFY_DB_DSN_WRITE"
DEFAULT_DSN_ENV = "ACQUITTIFY_DB_DSN"


def _get_dsn(write: bool) -> Optional[str]:
    if write:
        return os.getenv(WRITE_DSN_ENV) or os.getenv(DEFAULT_DSN_ENV)
    return os.getenv(READ_DSN_ENV) or os.getenv(DEFAULT_DSN_ENV)


@contextmanager
def get_conn(write: bool = False) -> Iterator[psycopg.Connection]:
    dsn = _get_dsn(write)
    if not dsn:
        raise RuntimeError(
            f"Missing database DSN. Set {READ_DSN_ENV} for read-only and {WRITE_DSN_ENV} for review writes."
        )
    with psycopg.connect(dsn) as conn:
        yield conn
