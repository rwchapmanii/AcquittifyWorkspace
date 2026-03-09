#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
if "" in sys.path:
    sys.path.remove("")

from app.db.session import get_session_factory  # noqa: E402
from app.services.dropbox_case_sync import sync_case_folders, list_case_folders  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root-path", dest="root_path", default=None)
    parser.add_argument("--print-only", action="store_true")
    args = parser.parse_args()

    if args.print_only:
        cases = list_case_folders(root_path=args.root_path)
        for case in cases:
            print(case.name)
        return 0

    session = get_session_factory()()
    try:
        result = sync_case_folders(session=session, root_path=args.root_path)
        print("Created casefiles:")
        for case in result.created:
            print(f"  + {case.name}")
        print("Existing casefiles:")
        for case in result.existing:
            print(f"  - {case.name}")
        print(f"Total: {len(result.created) + len(result.existing)}")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
