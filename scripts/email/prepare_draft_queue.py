#!/usr/bin/env python3
"""Pull inbox mail, attach style context, and write draft-ready queue entries."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

import numpy as np
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sentence_transformers import SentenceTransformer

SECRETS_DIR = Path("~/.openclaw/secrets").expanduser()
TOKEN_TEMPLATE = "gmail_token_{email}.json"
STYLE_DIR = Path("~/.openclaw/email_style").expanduser()
PROFILE_JSON = STYLE_DIR / "style_profile.json"
EMBED_FILE = STYLE_DIR / "exemplars_embeddings.npz"
META_FILE = STYLE_DIR / "exemplars_meta.jsonl"
DRAFT_DIR = STYLE_DIR / "draft_queue"


def load_profile() -> dict:
    return json.loads(PROFILE_JSON.read_text(encoding="utf-8"))


def load_style_index() -> tuple[np.ndarray, list[dict]]:
    embeddings = np.load(EMBED_FILE)["embeddings"]
    metas = [json.loads(line) for line in META_FILE.open(encoding="utf-8")]
    return embeddings, metas


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


def extract_body(msg: dict) -> str:
    payload = msg.get("payload", {})
    return decode_part(payload)


def decode_part(part: dict) -> str:
    mime = part.get("mimeType", "")
    data = part.get("body", {}).get("data")
    if data and mime.startswith("text/plain"):
        raw = base64.urlsafe_b64decode(data.encode("utf-8"))
        return raw.decode("utf-8", errors="ignore")
    parts = part.get("parts") or []
    texts = [decode_part(p) for p in parts]
    return "\n".join([t for t in texts if t]).strip()


def cosine_similarity(vec, matrix):
    vec_norm = vec / np.linalg.norm(vec)
    norms = matrix / np.linalg.norm(matrix, axis=1, keepdims=True)
    return np.dot(norms, vec_norm)


def prepare(email: str, query: str, max_msgs: int) -> None:
    creds = load_credentials(email)
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    profile = load_profile()
    embeddings, metas = load_style_index()
    model = SentenceTransformer("all-MiniLM-L6-v2")
    DRAFT_DIR.mkdir(parents=True, exist_ok=True)

    resp = service.users().messages().list(userId="me", q=query, labelIds=["INBOX"], maxResults=max_msgs).execute()
    messages = resp.get("messages", [])
    for meta in messages:
        msg = service.users().messages().get(userId="me", id=meta["id"], format="full").execute()
        headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
        body = extract_body(msg)
        summary = body[:600].strip().replace("\n", " ")
        text_for_embedding = f"Subject: {headers.get('subject','')}\n\n{summary}"
        vec = model.encode([text_for_embedding])[0]
        scores = cosine_similarity(vec, embeddings)
        top_idx = np.argsort(scores)[-3:][::-1]
        exemplars = [metas[i] | {"score": float(scores[i])} for i in top_idx]
        style_prompt = {
            "greeting": profile.get("top_greetings", [["Hi", 0]])[0][0],
            "closing": profile.get("top_closings", [["Thanks", 0]])[0][0],
            "avg_words": profile.get("avg_word_count"),
            "bullet_usage_pct": profile.get("bullet_usage_pct"),
        }
        draft_plan = {
            "message_id": msg["id"],
            "threadId": msg.get("threadId"),
            "from": headers.get("from"),
            "subject": headers.get("subject"),
            "summary": summary,
            "style_prompt": style_prompt,
            "style_examples": exemplars,
        }
        out_path = DRAFT_DIR / f"draft_{msg['id']}.json"
        out_path.write_text(json.dumps(draft_plan, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Queued draft context -> {out_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare draft-ready entries for inbox mail")
    parser.add_argument("--email", required=True)
    parser.add_argument("--query", default="label:unread -label:chats")
    parser.add_argument("--max", type=int, default=10)
    args = parser.parse_args()
    prepare(args.email, args.query, args.max)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
