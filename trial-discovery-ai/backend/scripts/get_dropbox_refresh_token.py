#!/usr/bin/env python3
"""
Interactive helper to generate a Dropbox *refresh token* for offline access.

It reads DROPBOX_APP_KEY and DROPBOX_APP_SECRET from the environment. For
convenience, it will also load them from the sibling `backend/.env` file
if present.

Usage:
  python3 \
    trial-discovery-ai/backend/scripts/get_dropbox_refresh_token.py
"""

from __future__ import annotations

import os
from pathlib import Path

import dropbox
from dropbox.oauth import DropboxOAuth2FlowNoRedirect


def _load_dotenv(env_path: Path) -> None:
    if not env_path.is_file():
        return

    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        # Allow quoted values in .env.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]

        os.environ.setdefault(key, value)


def _upsert_dotenv(env_path: Path, key: str, value: str) -> None:
    """
    Update or append `KEY=value` in a .env file while preserving unrelated lines.
    """
    if env_path.is_file():
        lines = env_path.read_text(encoding="utf-8").splitlines(keepends=True)
    else:
        lines = []

    updated = False
    out: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            out.append(line)
            continue

        existing_key, _sep, rest = line.partition("=")
        existing_key = existing_key.strip()
        if existing_key != key:
            out.append(line)
            continue

        # Preserve trailing inline comment: KEY=... # comment
        comment = ""
        if "#" in rest:
            value_before_hash, hash_, after_hash = rest.partition("#")
            _ = value_before_hash
            comment = hash_ + after_hash

        newline = "\n" if line.endswith("\n") else ""
        out.append(f"{key}={value} {comment}".rstrip() + newline)
        updated = True

    if not updated:
        if out and not out[-1].endswith("\n"):
            out[-1] = out[-1] + "\n"
        if out and out[-1].strip():
            out.append("\n")
        out.append(f"{key}={value}\n")

    env_path.write_text("".join(out), encoding="utf-8")


def main() -> int:
    # scripts/ is inside backend/, so backend/.env is at parents[1] / ".env"
    backend_env = Path(__file__).resolve().parents[1] / ".env"
    _load_dotenv(backend_env)

    app_key = (os.getenv("DROPBOX_APP_KEY") or "").strip()
    app_secret = (os.getenv("DROPBOX_APP_SECRET") or "").strip()
    if not app_key or not app_secret:
        print("Missing Dropbox app credentials.")
        print("Set DROPBOX_APP_KEY and DROPBOX_APP_SECRET (in env or backend/.env).")
        return 2

    auth_flow = DropboxOAuth2FlowNoRedirect(
        app_key,
        app_secret,
        token_access_type="offline",
    )
    authorize_url = auth_flow.start()

    print("1. Open this URL in your browser and click Allow:")
    print(authorize_url)
    print()
    auth_code = input("2. Paste the authorization code here: ").strip()
    oauth_result = auth_flow.finish(auth_code)

    refresh_token = getattr(oauth_result, "refresh_token", None)
    if not refresh_token:
        print()
        print("No refresh token was returned.")
        print("Make sure the OAuth flow requested offline access (token_access_type=offline).")
        return 1

    # Persist refresh token to backend/.env so the app can refresh access tokens automatically.
    _upsert_dotenv(backend_env, "DROPBOX_REFRESH_TOKEN", refresh_token)
    # Ensure key/secret are present too (helps if user only set env vars temporarily).
    _upsert_dotenv(backend_env, "DROPBOX_APP_KEY", app_key)
    _upsert_dotenv(backend_env, "DROPBOX_APP_SECRET", app_secret)

    print()
    print(f"Wrote DROPBOX_REFRESH_TOKEN to {backend_env} (ends with ***{refresh_token[-6:]})")

    # Quick verification: call Dropbox API using refresh_token.
    try:
        client = dropbox.Dropbox(
            oauth2_refresh_token=refresh_token,
            app_key=app_key,
            app_secret=app_secret,
        )
        acct = client.users_get_current_account()
        print("Dropbox API connection: OK")
        print(f"  account_id: ***{acct.account_id[-6:]}")
    except Exception as e:
        print("Dropbox API connection: FAILED")
        print(f"  error: {type(e).__name__}: {e}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
