#!/usr/bin/env python3
"""Derive Ron's email style profile from the exported sent mail corpus."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
import re
from pathlib import Path

DEFAULT_CORPUS = Path("~/.openclaw/email_style/sent.jsonl").expanduser()
GREETING_RE = re.compile(r"^(hi|hello|good\s+(morning|afternoon|evening)|dear)[\w,\s.-]*$", re.IGNORECASE)
CLOSING_RE = re.compile(r"^(thanks|thank you|best|kind regards|regards|sincerely|appreciate|warmly)[\w,\s.-]*$", re.IGNORECASE)
PROFILE_JSON = Path("~/.openclaw/email_style/style_profile.json").expanduser()
PROFILE_MD = Path("~/.openclaw/email_style/style_profile.md").expanduser()


def normalize_line(line: str) -> str:
    return line.strip().lower()


def detect_greeting(lines: list[str]) -> str | None:
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if GREETING_RE.match(stripped):
            return stripped
    return None


def detect_closing(lines: list[str]) -> str | None:
    for line in reversed(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if CLOSING_RE.match(stripped):
            return stripped
    return None


def analyze(corpus_path: Path) -> tuple[dict, str]:
    greetings = Counter()
    closings = Counter()
    bodies: list[str] = []
    bullet_emails = 0
    emails = 0

    with corpus_path.open(encoding="utf-8") as fh:
        for line in fh:
            record = json.loads(line)
            body = record.get("body", "").strip()
            if not body:
                continue
            emails += 1
            bodies.append(body)
            lines = body.splitlines()
            greeting = detect_greeting(lines)
            closing = detect_closing(lines)
            if greeting:
                greetings[greeting] += 1
            if closing:
                closings[closing] += 1
            if any(l.strip().startswith(("- ", "•", "* ")) for l in lines):
                bullet_emails += 1

    word_counts = [len(body.split()) for body in bodies]
    paragraph_counts = [len([p for p in body.split("\n\n") if p.strip()]) for body in bodies]

    profile = {
        "email_count": emails,
        "avg_word_count": statistics.mean(word_counts) if word_counts else 0,
        "median_word_count": statistics.median(word_counts) if word_counts else 0,
        "avg_paragraphs": statistics.mean(paragraph_counts) if paragraph_counts else 0,
        "bullet_usage_pct": round((bullet_emails / emails) * 100, 2) if emails else 0,
        "top_greetings": greetings.most_common(5),
        "top_closings": closings.most_common(5),
    }

    md_lines = [
        "# Email Style Profile",
        f"**Samples analyzed:** {emails}",
        f"**Average length:** {profile['avg_word_count']:.1f} words",
        f"**Median length:** {profile['median_word_count']:.1f} words",
        f"**Average paragraphs:** {profile['avg_paragraphs']:.1f}",
        f"**Uses bullet lists:** {profile['bullet_usage_pct']}% of replies",
        "",
        "## Greetings",
    ]
    for text, count in profile["top_greetings"]:
        md_lines.append(f"- {text} ({count})")
    md_lines.append("\n## Closings")
    for text, count in profile["top_closings"]:
        md_lines.append(f"- {text} ({count})")

    md_lines.append("\n## Tone & Notes")
    md_lines.append("- Strive for the above greeting/closing patterns.")
    md_lines.append("- Keep replies between the average and median length unless the context demands more detail.")

    return profile, "\n".join(md_lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create style profile from sent corpus")
    parser.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    args = parser.parse_args()
    corpus_path = Path(args.corpus).expanduser()
    profile, markdown = analyze(corpus_path)
    PROFILE_JSON.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_JSON.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    PROFILE_MD.write_text(markdown, encoding="utf-8")
    print(f"Wrote {PROFILE_JSON} and {PROFILE_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
