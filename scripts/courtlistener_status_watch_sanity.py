#!/usr/bin/env python3
"""Sanity-check that watch mode updates the status report."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path


def main() -> None:
    output_path = Path("reports/courtlistener_ingest_status_watch_sanity.md")
    if output_path.exists():
        output_path.unlink()

    cmd = [
        sys.executable,
        "scripts/courtlistener_ingest_status.py",
        "--format",
        "md",
        "--output",
        str(output_path),
        "--watch",
        "1",
        "--iterations",
        "2",
        "--tail",
        "1",
    ]
    subprocess.run(cmd, check=True)

    if not output_path.exists():
        raise SystemExit("watch output not created")

    content = output_path.read_text(encoding="utf-8")
    if "CourtListener Ingestion Status" not in content:
        raise SystemExit("unexpected output contents")

    print("ok")


if __name__ == "__main__":
    main()
