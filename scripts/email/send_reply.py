#!/usr/bin/env python3
"""Send a reply directly via Gmail API (after manual edits)."""

from __future__ import annotations

import argparse
import base64
import json
from email.message import EmailMessage
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SECRETS_DIR = Path("~/.openclaw/secrets").expanduser()
TOKEN_TEMPLATE = "gmail_token_{email}.json"


def load_credentials(email: str) -> Credentials:
    token_path = SECRETS_DIR / TOKEN_TEMPLATE.format(email=email.replace("@", "_"))
    token_data = json.loads(token_path.read_text(encoding="utf-8"))
    creds = Credentials(
        token=None,
        refresh_token=token_data["refresh_token"],
        token_uri=token_data["token_uri"],
        client_id=token_data["client_id"],
        client_secret=token_data["client_secret"],
        scopes=token_data["scopes"],
    )
    creds.refresh(Request())
    return creds


def send(email: str, queue_path: Path, body_path: Path) -> None:
    queue_entry = json.loads(queue_path.read_text(encoding="utf-8"))
    body = body_path.read_text(encoding="utf-8")
    creds = load_credentials(email)
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    msg = EmailMessage()
    msg["To"] = queue_entry.get("from")
    subject = queue_entry.get("subject") or ""
    if subject.lower().startswith("re:"):
        msg["Subject"] = subject
    else:
        msg["Subject"] = f"Re: {subject}" if subject else "Re:"
    msg.set_content(body)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    send_body = {"raw": raw}
    if queue_entry.get("threadId"):
        send_body["threadId"] = queue_entry["threadId"]
    sent = service.users().messages().send(userId="me", body=send_body).execute()
    print(f"Sent message id: {sent.get('id')}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Send a reply using a prepared queue entry")
    parser.add_argument("--email", required=True)
    parser.add_argument("--queue", required=True)
    parser.add_argument("--body", required=True, help="Path to final text (after edits)")
    args = parser.parse_args()
    send(args.email, Path(args.queue), Path(args.body))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
