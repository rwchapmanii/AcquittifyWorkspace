#!/usr/bin/env python3
"""Export Ron's sent mail to a local style corpus (JSONL, git-ignored)."""

from __future__ import annotations

import argparse
import base64
import json
import re
import html as html_lib
from pathlib import Path
from typing import Iterable

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SECRETS_DIR = Path("~/.openclaw/secrets").expanduser()
CLIENT_FILE = SECRETS_DIR / "gmail_oauth.json"
TOKEN_TEMPLATE = "gmail_token_{email}.json"
DEFAULT_OUTPUT = Path("~/.openclaw/email_style/sent.jsonl").expanduser()


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


def list_messages(service, label_ids: list[str], max_messages: int | None) -> Iterable[str]:
    kwargs = {"userId": "me", "labelIds": label_ids, "maxResults": 500}
    fetched = 0
    while True:
        resp = service.users().messages().list(**kwargs).execute()
        for msg in resp.get("messages", []):
            yield msg["id"]
            fetched += 1
            if max_messages and fetched >= max_messages:
                return
        if "nextPageToken" not in resp:
            return
        kwargs["pageToken"] = resp["nextPageToken"]


def extract_text(payload: dict) -> str:
    mime = payload.get("mimeType", "")
    body = payload.get("body", {})
    data = body.get("data")
    if data and mime.startswith("text/"):
        raw = base64.urlsafe_b64decode(data.encode("utf-8"))
        try:
            decoded = raw.decode("utf-8")
        except UnicodeDecodeError:
            decoded = raw.decode("latin-1", errors="ignore")
        if mime == "text/html":
            return html_to_text(decoded)
        return decoded
    parts = payload.get("parts") or []
    texts = [extract_text(part) for part in parts]
    return "\n".join([t for t in texts if t])


HTML_TAG_RE = re.compile(r"<[^>]+>")
QUOTE_RE = re.compile(r"^>+|\bon .*wrote:.*$", re.IGNORECASE)
SIGNATURE_RE = re.compile(r"^--\s*$")



def html_to_text(value: str) -> str:
    text = HTML_TAG_RE.sub(" ", value)
    return html_lib.unescape(re.sub(r"\s+", " ", text))

def clean_body(text: str) -> str:
    lines = []
    signature_hit = False
    for line in text.splitlines():
        stripped = line.strip()
        if signature_hit:
            continue
        if SIGNATURE_RE.match(stripped):
            signature_hit = True
            continue
        if QUOTE_RE.match(stripped):
            continue
        lines.append(line.rstrip())
    cleaned = "\n".join(lines).strip()
    # collapse triple newlines
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned


def export_sent(email: str, output_path: Path, max_messages: int | None) -> None:
    creds = load_credentials(email)
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        for msg_id in list_messages(service, label_ids=["SENT"], max_messages=max_messages):
            msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
            payload = msg.get("payload", {})
            body = clean_body(extract_text(payload))
            if not body:
                continue
            headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
            record = {
                "id": msg["id"],
                "threadId": msg.get("threadId"),
                "date": headers.get("date"),
                "subject": headers.get("subject"),
                "to": headers.get("to"),
                "cc": headers.get("cc"),
                "body": body,
            }
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"Exported sent mail to {output_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Export sent mail for style analysis")
    parser.add_argument("--email", required=True)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--max", type=int, default=500, help="Max messages to export (0 = all)")
    args = parser.parse_args()
    max_messages = args.max if args.max > 0 else None
    export_sent(args.email, Path(args.output).expanduser(), max_messages)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
