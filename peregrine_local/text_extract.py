from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path


def extract_text_from_html(raw: str) -> str:
    class _Extractor(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.parts: list[str] = []

        def handle_data(self, data: str) -> None:
            if data and data.strip():
                self.parts.append(data.strip())

    parser = _Extractor()
    parser.feed(raw)
    return "\n".join(parser.parts)


def extract_text_from_eml(path: Path, raw: str) -> str:
    try:
        import mailparser
    except Exception:
        return raw

    try:
        mail = mailparser.parse_from_bytes(raw.encode("utf-8", errors="ignore"))
    except Exception:
        return raw

    parts: list[str] = []
    if mail.subject:
        parts.append(f"Subject: {mail.subject}")
    if mail.from_:
        parts.append(f"From: {mail.from_}")
    if mail.to:
        parts.append(f"To: {mail.to}")
    if mail.cc:
        parts.append(f"Cc: {mail.cc}")
    if mail.date:
        parts.append(f"Date: {mail.date}")

    if mail.text_plain:
        parts.append("\n".join(mail.text_plain))
    elif mail.text_html:
        parts.append(extract_text_from_html("\n".join(mail.text_html)))

    return "\n".join(parts) if parts else raw
