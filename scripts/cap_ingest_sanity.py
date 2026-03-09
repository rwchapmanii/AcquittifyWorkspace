#!/usr/bin/env python3
"""Sanity-check CAP ingest outputs (manifest + checksums)."""

from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    base = Path("acquittify-data")
    manifest_path = base / "ingest" / "manifest" / "manifest.json"
    checksums_path = base / "ingest" / "manifest" / "checksums.txt"

    if not manifest_path.exists():
        raise SystemExit("manifest.json not found")
    if not checksums_path.exists():
        raise SystemExit("checksums.txt not found")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    ingest_files = manifest.get("ingest_files") or []
    if not ingest_files:
        raise SystemExit("manifest ingest_files is empty")

    checksum_lines = [line for line in checksums_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(checksum_lines) != len(ingest_files):
        raise SystemExit("checksum count does not match ingest_files")

    print("ok")


if __name__ == "__main__":
    main()
