#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from typing import Iterable

import requests


def _candidate_urls() -> Iterable[str]:
    env_url = (os.getenv("INCOURT_SERVER_URL") or "").strip()
    if env_url:
        yield env_url
        return
    env_port = (os.getenv("INCOURT_SERVER_PORT") or "").strip()
    if env_port:
        yield f"http://localhost:{env_port}"
        return
    yield "http://localhost:8777"
    yield "http://localhost:8778"


def _check(url: str) -> bool:
    try:
        resp = requests.get(f"{url}/health", timeout=2)
        return resp.status_code == 200
    except Exception:
        return False


def main() -> int:
    ok_any = False
    for url in _candidate_urls():
        ok = _check(url)
        status = "ok" if ok else "down"
        print(f"{url}: {status}")
        ok_any = ok_any or ok
    return 0 if ok_any else 1


if __name__ == "__main__":
    sys.exit(main())
