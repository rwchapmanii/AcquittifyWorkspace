#!/usr/bin/env python3
"""Sanity check for resolving CourtListener bulk-data S3 keys.

Usage:
  .venv/bin/python scripts/courtlistener_bulk_key_check.py --entity opinion-texts
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ingestion_infra.config import Settings
from ingestion_infra.sources.s3_bulk import S3BulkSource


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve CourtListener bulk-data keys")
    parser.add_argument("--entity", default="opinion-texts", help="Bulk entity name")
    args = parser.parse_args()

    source = S3BulkSource(Settings())
    keys = source.resolve_keys(args.entity)
    print(f"entity={args.entity} keys={len(keys)}")
    for key in keys[:10]:
        print(f"- {key}")

    return 0 if keys else 2


if __name__ == "__main__":
    raise SystemExit(main())
