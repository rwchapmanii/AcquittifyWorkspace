#!/usr/bin/env python3
"""One-time Gmail OAuth helper."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
]
DEFAULT_CLIENT_PATH = Path("~/.openclaw/secrets/gmail_oauth.json").expanduser()
TOKEN_TEMPLATE = "gmail_token_{email}.json"


def load_client_config(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    redirect_uri = data.get("redirect_uri") or "urn:ietf:wg:oauth:2.0:oob"
    return {
        "installed": {
            "client_id": data["client_id"],
            "client_secret": data["client_secret"],
            "redirect_uris": [redirect_uri],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def write_token(email: str, creds, client_config: dict, secrets_dir: Path) -> Path:
    secrets_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "email": email,
        "client_id": client_config["installed"]["client_id"],
        "client_secret": client_config["installed"]["client_secret"],
        "token_uri": creds.token_uri,
        "refresh_token": creds.refresh_token,
        "scopes": SCOPES,
    }
    token_path = secrets_dir / TOKEN_TEMPLATE.format(email=email.replace("@", "_"))
    token_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return token_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Gmail OAuth flow")
    parser.add_argument("--email", required=True, help="Mailbox to authorize")
    parser.add_argument(
        "--client-path",
        default=str(DEFAULT_CLIENT_PATH),
        help=f"Path to oauth client JSON (default: {DEFAULT_CLIENT_PATH})",
    )
    parser.add_argument(
        "--secrets-dir",
        default=str(DEFAULT_CLIENT_PATH.parent),
        help="Directory to store refresh tokens",
    )
    args = parser.parse_args()

    client_path = Path(args.client_path).expanduser()
    secrets_dir = Path(args.secrets_dir).expanduser()
    if not client_path.exists():
        print(f"Client config not found: {client_path}", file=sys.stderr)
        return 1

    config = load_client_config(client_path)
    flow = InstalledAppFlow.from_client_config(config, SCOPES)
    redirect_uri = config["installed"]["redirect_uris"][0]
    flow.redirect_uri = redirect_uri
    auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent")
    print("\nOpen this URL in your browser and approve access:\n")
    print(auth_url)
    auth_code = input("\nPaste the verification code here: ").strip()
    if not auth_code:
        print("No code provided", file=sys.stderr)
        return 1
    flow.fetch_token(code=auth_code)
    creds = flow.credentials
    token_path = write_token(args.email, creds, config, secrets_dir)
    print(f"Refresh token stored at {token_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
