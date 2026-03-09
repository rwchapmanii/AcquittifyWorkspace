from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import List, Dict, Optional


CASE_TITLE_REGEX = re.compile(r"\b([A-Z][A-Za-z0-9.&'\- ]+\s+v\.?\s+[A-Z][A-Za-z0-9.&'\- ]+)\b")
DOCKET_REGEX = re.compile(r"\b(No\.?\s*)?(\d{1,2}:\d{2}-cr-\d{2,6})\b", re.IGNORECASE)
DOCUMENT_DOCKET_REGEX = re.compile(r"\bDocument\s+(\d+)\b", re.IGNORECASE)
PAGE_ID_REGEX = re.compile(r"\b(?:Page\s*ID|PageID|PGID)\s*[\.:#-]?\s*(\d+)\b", re.IGNORECASE)
TRANSCRIPT_PAGE_REGEX = re.compile(r"\bPage\s+(\d+)\s+of\s+\d+\b", re.IGNORECASE)
TRANSCRIPT_PAGE_ALT_REGEX = re.compile(r"\bPage\s+(\d+)\b", re.IGNORECASE)
WITNESS_REGEX = re.compile(r"\bTESTIMONY\s+OF\s+([A-Z][A-Z\s.'\-]+)\b")
EXAM_REGEX = re.compile(r"\b(DIRECT|CROSS|REDIRECT|RECROSS)\s+EXAMINATION\b", re.IGNORECASE)
QUESTIONER_REGEX = re.compile(r"\bQUESTIONS\s+BY\s+([A-Z][A-Z\s.'\-]+)\b", re.IGNORECASE)


@dataclass
class TranscriptPage:
    page_index: int
    text: str
    transcript_page: Optional[int]
    page_id: Optional[int]
    witness: Optional[str]
    exam: Optional[str]
    questioner: Optional[str]


def _clean_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def _title_case(name: str) -> str:
    return " ".join([part.capitalize() for part in name.split()])


def extract_case_title(text: str) -> Optional[str]:
    for line in text.splitlines():
        line = _clean_line(line)
        match = CASE_TITLE_REGEX.search(line)
        if match:
            return match.group(1).strip()
    return None


def extract_docket_number(text: str) -> Optional[str]:
    lines = [
        _clean_line(line)
        for line in text.splitlines()
        if _clean_line(line)
    ]
    heading = " ".join(lines[:10])
    match = DOCUMENT_DOCKET_REGEX.search(heading)
    if match:
        return match.group(1)
    match = DOCKET_REGEX.search(heading)
    if match:
        return match.group(2)
    return None


def _require_fitz():
    try:
        import fitz  # PyMuPDF
    except Exception as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError(
            "PyMuPDF (fitz) is required to parse transcript PDFs. "
            "Install it with: pip install PyMuPDF"
        ) from exc
    return fitz


def _extract_transcript_page(text: str) -> Optional[int]:
    match = TRANSCRIPT_PAGE_REGEX.search(text)
    if match:
        return int(match.group(1))
    match = TRANSCRIPT_PAGE_ALT_REGEX.search(text)
    if match:
        return int(match.group(1))
    return None


def _extract_page_id(text: str) -> Optional[int]:
    match = PAGE_ID_REGEX.search(text)
    if not match:
        return None
    return int(match.group(1))


def parse_transcript_pdf(path: Path) -> Dict:
    fitz = _require_fitz()
    pages: List[TranscriptPage] = []

    case_title = None
    docket_number = None
    witness_roster = set()

    current_witness = None
    current_exam = None
    current_questioner = None

    with fitz.open(path) as doc:
        for idx in range(doc.page_count):
            page = doc.load_page(idx)
            text = page.get_text("text") or ""
            if not docket_number:
                docket_number = extract_docket_number(text)

            if idx < 2 and not case_title:
                case_title = extract_case_title(text)

            transcript_page = _extract_transcript_page(text)
            page_id = _extract_page_id(text)

            lines = [
                _clean_line(line)
                for line in text.splitlines()
                if _clean_line(line)
            ]

            for line in lines:
                witness_match = WITNESS_REGEX.search(line)
                if witness_match:
                    current_witness = _title_case(witness_match.group(1).strip())
                    witness_roster.add(current_witness)

                exam_match = EXAM_REGEX.search(line)
                if exam_match:
                    current_exam = exam_match.group(1).lower()

                questioner_match = QUESTIONER_REGEX.search(line)
                if questioner_match:
                    current_questioner = _title_case(questioner_match.group(1).strip())

            pages.append(
                TranscriptPage(
                    page_index=idx,
                    text=text.strip(),
                    transcript_page=transcript_page,
                    page_id=page_id,
                    witness=current_witness,
                    exam=current_exam,
                    questioner=current_questioner,
                )
            )

        page_count = doc.page_count

    return {
        "case_title": case_title,
        "docket_number": docket_number,
        "pages": pages,
        "witnesses": sorted(witness_roster),
        "page_count": page_count,
    }
