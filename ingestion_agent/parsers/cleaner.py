"""Normalization and cleaning for legal texts."""

from ingestion_agent.utils.text import normalize_line_endings
import re


TABLE_OF_AUTHORITIES_RE = re.compile(r"\bTABLE OF AUTHORITIES\b", re.IGNORECASE)
PAGE_NUMBER_RE = re.compile(r"^\s*(?:-\s*)?\d+\s*(?:-\s*)?$")
HEADER_FOOTER_RE = re.compile(r"^\s*Page\s+\d+\s+of\s+\d+\s*$", re.IGNORECASE)
JUDGE_SIGNATURE_RE = re.compile(r"^\s*(/s/|s/)\s+.+$", re.IGNORECASE)
JUDGE_TITLE_RE = re.compile(
    r"^\s*(Chief\s+)?(United\s+States\s+)?(District|Circuit|Magistrate|Bankruptcy)\s+Judge\b",
    re.IGNORECASE,
)
SIGNED_BY_RE = re.compile(r"^\s*Signed\s+by\s+.+$", re.IGNORECASE)


def remove_tables_of_authorities(text: str) -> str:
    """Remove table of authorities sections when detected."""
    if not TABLE_OF_AUTHORITIES_RE.search(text):
        return text
    lines = text.splitlines()
    cleaned = []
    skipping = False
    for line in lines:
        if TABLE_OF_AUTHORITIES_RE.search(line):
            skipping = True
            continue
        if skipping and line.strip() == "":
            skipping = False
            continue
        if not skipping:
            cleaned.append(line)
    return "\n".join(cleaned)


def remove_headers_footers(text: str) -> str:
    """Remove common headers and footers."""
    lines = text.splitlines()
    cleaned = []
    for line in lines:
        if HEADER_FOOTER_RE.match(line):
            continue
        if PAGE_NUMBER_RE.match(line.strip()):
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def remove_judge_signatures(text: str) -> str:
    """Remove common judge signature blocks from the end of opinions."""
    lines = text.splitlines()
    end = len(lines) - 1
    while end >= 0:
        line = lines[end].strip()
        if not line:
            end -= 1
            continue
        if JUDGE_SIGNATURE_RE.match(line) or JUDGE_TITLE_RE.match(line) or SIGNED_BY_RE.match(line):
            end -= 1
            continue
        break
    return "\n".join(lines[: end + 1])


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace and line breaks."""
    text = normalize_line_endings(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_text(text: str) -> str:
    """Clean raw legal text for downstream parsing."""
    text = normalize_line_endings(text)
    text = remove_tables_of_authorities(text)
    text = remove_headers_footers(text)
    text = remove_judge_signatures(text)
    text = normalize_whitespace(text)
    return text
