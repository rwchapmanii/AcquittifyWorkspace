#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "trial-discovery-ai" / "backend"

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(BACKEND_DIR))
if "" in sys.path:
    sys.path.remove("")

from case_manager import ensure_case_by_id  # noqa: E402
from app.services.dropbox_case_sync import list_case_folders  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root-path", dest="root_path", default=None)
    parser.add_argument("--print-only", action="store_true")
    args = parser.parse_args()

    cases = list_case_folders(root_path=args.root_path)
    if args.print_only:
        for case in cases:
            print(case.name)
        return 0

    created = 0
    for case in cases:
        ensure_case_by_id(case.name, case.name, dropbox_path=case.path)
        created += 1

    print(f"Synced case folders: {created}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
