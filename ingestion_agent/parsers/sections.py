"""Section parsing for legal opinions."""

from __future__ import annotations

from typing import List, Tuple
import re


SECTION_PATTERNS = {
    "facts": [r"\bFACTS\b", r"\bBACKGROUND\b"],
    "issues": [r"\bISSUES?\b", r"\bQUESTION PRESENTED\b"],
    "reasoning": [r"\bANALYSIS\b", r"\bDISCUSSION\b", r"\bREASONING\b"],
    "holding": [r"\bHOLDING\b"],
    "disposition": [r"\bDISPOSITION\b", r"\bCONCLUSION\b", r"\bORDER\b"],
}


def _compile_heading_map() -> List[Tuple[str, re.Pattern]]:
    compiled = []
    for section, patterns in SECTION_PATTERNS.items():
        for pattern in patterns:
            compiled.append((section, re.compile(pattern, re.IGNORECASE)))
    return compiled


HEADING_MAP = _compile_heading_map()


def parse_sections(text: str) -> List[Tuple[str, str]]:
    """Parse text into labeled sections using heading heuristics."""
    lines = text.splitlines()
    sections: List[Tuple[str, str]] = []
    current_label = "body"
    current_lines: List[str] = []

    def flush() -> None:
        nonlocal current_lines
        if current_lines:
            sections.append((current_label, "\n".join(current_lines).strip()))
            current_lines = []

    for line in lines:
        matched_label = None
        for label, pattern in HEADING_MAP:
            if pattern.search(line.strip()) and line.strip().isupper():
                matched_label = label
                break
        if matched_label:
            flush()
            current_label = matched_label
            continue
        current_lines.append(line)

    flush()
    return [(label, content) for label, content in sections if content]
