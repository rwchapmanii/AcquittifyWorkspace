from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz")

from acquittify.ingest.transcript_parser import PAGE_ID_REGEX, parse_transcript_pdf


EXEMPLAR_PATH = Path(
    "Acquittify Storage/Corpus/Trial Transcripts and Docket Reports/00. Sherman Full Transcripts (Combined)-2.pdf"
)


def test_transcript_parsing_exemplar():
    if not EXEMPLAR_PATH.exists():
        pytest.skip("Exemplar transcript PDF not found.")

    result = parse_transcript_pdf(EXEMPLAR_PATH)
    assert result.get("case_title"), "case title should be extracted"
    assert result.get("docket_number"), "docket number should be extracted"

    pages = result.get("pages", [])
    page_ids = [p.page_id for p in pages if p.page_id]
    transcript_pages = [p.transcript_page for p in pages if p.transcript_page]

    assert len(page_ids) >= 2, "should extract PageID on at least two pages"
    assert len(transcript_pages) >= 2, "should extract transcript page numbers"

    witnesses = {w.lower() for w in result.get("witnesses", [])}
    if "david alm" in witnesses or "edward miller" in witnesses:
        assert "david alm" in witnesses
        assert "edward miller" in witnesses


def test_page_id_regex_accepts_dot_separator():
    header = "Case 5:21-cr-20393-JEL-KGA ECF No. 345, PageID.6244 Filed 03/14/25 Page 1"
    match = PAGE_ID_REGEX.search(header)
    assert match
    assert match.group(1) == "6244"
