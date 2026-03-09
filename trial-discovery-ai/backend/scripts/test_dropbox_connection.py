#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
if "" in sys.path:
    sys.path.remove("")

from app.core.config import get_settings
from app.storage.dropbox import DropboxClient


def main() -> int:
    settings = get_settings()
    root_path = settings.dropbox_root_path or ""

    print("Dropbox settings present:")
    print(f"  access_token: {bool(settings.dropbox_access_token)}")
    print(f"  refresh_token: {bool(settings.dropbox_refresh_token)}")
    print(f"  app_key: {bool(settings.dropbox_app_key)}")
    print(f"  app_secret: {bool(settings.dropbox_app_secret)}")
    print(f"  team_member_id: {bool(settings.dropbox_team_member_id)}")
    print(f"  root_path: {root_path!r}")

    client = DropboxClient()
    acct = client._client.users_get_current_account()
    print("Dropbox API connection: OK")
    print(f"  account_id: ***{acct.account_id[-6:]}")

    result = client._client.files_list_folder(root_path)
    print("List folder: OK")
    print(f"  entries_returned: {len(result.entries)}")
    print(f"  has_more: {result.has_more}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
