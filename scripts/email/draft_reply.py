#!/usr/bin/env python3
"""Generate a stylistic reply via OpenAI and (optionally) create a Gmail draft."""

from __future__ import annotations

import argparse
import base64
import json
import os
from email.message import EmailMessage
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from openai import OpenAI

SECRETS_DIR = Path("~/.openclaw/secrets").expanduser()
TOKEN_TEMPLATE = "gmail_token_{email}.json"
STYLE_DIR = Path("~/.openclaw/email_style").expanduser()
PROFILE_JSON = STYLE_DIR / "style_profile.json"
DRAFT_TEXT_DIR = STYLE_DIR / "drafts"
DEFAULT_MODEL = os.getenv("EMAIL_DRAFT_MODEL", "gpt-4o-mini")


def load_profile() -> dict:
    return json.loads(PROFILE_JSON.read_text(encoding="utf-8"))


def load_queue_entry(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_style_prompt(profile: dict) -> str:
    greeting = profile.get("top_greetings", [["Hi", 0]])[0][0]
    closing = profile.get("top_closings", [["Thanks", 0]])[0][0]
    avg_words = profile.get("avg_word_count", 400)
    bullet_pct = profile.get("bullet_usage_pct", 0)
    return (
        "You are Ron Chapman, a federal criminal-defense attorney."
        f" Use professional, decisive language. Preferred greeting: '{greeting}'."
        f" Preferred closing: '{closing}'. Aim for {avg_words:.0f} words unless a shorter reply suffices."
        f" Bullet lists are used in ~{bullet_pct}% of replies—only include them when clarifying multi-step actions."
    )


def call_openai(prompt: str, summary: str, examples: list[dict]) -> str:
    client = OpenAI()
    example_block = "\n\n".join(
        [f"Example subject: {ex.get('subject')}\n{ex.get('preview')}" for ex in examples]
    )
    user_content = (
        f"Incoming email summary:\n{summary}\n\n"
        f"Reference style examples:\n{example_block}\n\n"
        "Write Ron's reply in first person. Include any decisive next steps." \
        " Output plain text (no markdown)."
    )
    response = client.responses.create(
        model=DEFAULT_MODEL,
        input=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_content},
        ],
    )
    content = response.output[0].content[0].text
    return content.strip()


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


def create_gmail_draft(email: str, queue_entry: dict, body: str) -> dict:
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
    create_body = {"message": {"raw": raw}}
    if queue_entry.get("threadId"):
        create_body["message"]["threadId"] = queue_entry["threadId"]
    draft = service.users().drafts().create(userId="me", body=create_body).execute()
    return draft


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a reply and optionally create a Gmail draft")
    parser.add_argument("--email", required=True)
    parser.add_argument("--queue", required=True, help="Path to queue JSON (from prepare_draft_queue)")
    parser.add_argument("--no-draft", action="store_true", help="Skip creating Gmail draft (just save text)")
    args = parser.parse_args()

    profile = load_profile()
    queue_entry = load_queue_entry(Path(args.queue))
    prompt = build_style_prompt(profile)
    draft_text = call_openai(prompt, queue_entry.get("summary", ""), queue_entry.get("style_examples", []))
    DRAFT_TEXT_DIR.mkdir(parents=True, exist_ok=True)
    draft_path = DRAFT_TEXT_DIR / f"draft_{queue_entry['message_id']}.txt"
    draft_path.write_text(draft_text, encoding="utf-8")
    print(f"Draft text saved to {draft_path}")

    if not args.no_draft:
        draft = create_gmail_draft(args.email, queue_entry, draft_text)
        print(f"Created Gmail draft: {draft.get('id')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
