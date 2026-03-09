#!/usr/bin/env python3
"""Sanity-check that download_federal logging writes JSONL entries."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from scripts.download_federal import _append_download_log


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "download_federal.log"
        payload = {"ts": "2099-01-01T00:00:00Z", "event": "checkpoint", "slug": "us"}
        _append_download_log(log_path, payload)
        data = log_path.read_text(encoding="utf-8").strip().splitlines()
        if not data:
            raise SystemExit("No log lines written")
        parsed = json.loads(data[-1])
        if parsed.get("event") != "checkpoint":
            raise SystemExit("Unexpected log payload")
    print("ok: download log writes JSONL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
