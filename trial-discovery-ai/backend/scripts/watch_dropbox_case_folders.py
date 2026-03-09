#!/usr/bin/env python3
from __future__ import annotations

import argparse
import time
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
if "" in sys.path:
    sys.path.remove("")

from app.db.session import get_session_factory  # noqa: E402
from app.services.dropbox_case_sync import sync_case_folders  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root-path", dest="root_path", default=None)
    parser.add_argument("--interval", type=int, default=300)
    args = parser.parse_args()

    session_factory = get_session_factory()

    print("Watching Dropbox case folders...")
    while True:
        session = session_factory()
        try:
            result = sync_case_folders(session=session, root_path=args.root_path)
            for case in result.created:
                print(f"[new] {case.name}")
        finally:
            session.close()
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
