from acquittify.chunking import chunk_text
from acquittify.config import CHUNK_SIZE_CHARS


def test_chunk_text_respects_size():
    sentence = "This is a test sentence about Fed. R. Crim. P. 16 and Brady disclosure."
    text = " ".join([sentence for _ in range(120)])
    chunks = chunk_text(text)
    assert chunks, "expected chunks for legal signal text"
    assert all(len(c) <= CHUNK_SIZE_CHARS * 1.1 for c in chunks)


def test_chunk_text_filters_headers():
    text = "UNITED STATES COURT OF APPEALS\n\nTABLE OF CONTENTS\n\nPage 1 of 10"
    chunks = chunk_text(text)
    assert chunks == []


def test_chunk_text_keeps_legal_signal():
    text = (
        "The court held in Smith v. Jones, 123 F.3d 456 (9th Cir. 2001), "
        "that Fed. R. Crim. P. 16 requires disclosure."
    )
    chunks = chunk_text(text)
    assert len(chunks) == 1
