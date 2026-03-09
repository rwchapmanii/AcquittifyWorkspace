"""Text helpers for cleaning and chunking."""

from __future__ import annotations

import re
from typing import List


def normalize_line_endings(text: str) -> str:
    """Normalize line endings to Unix style."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def strip_html(text: str) -> str:
    """Remove HTML tags and decode basic entities."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ")
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    return text


def split_paragraphs(text: str) -> List[str]:
    """Split text into paragraphs using blank lines."""
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
