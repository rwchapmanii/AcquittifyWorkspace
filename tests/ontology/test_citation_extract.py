from acquittify.ontology.citation_extract import extract_citation_mentions



def test_extract_citations_with_offsets() -> None:
    text = "Under Carroll, 267 U.S. 132, and Ross, 456 U.S. 798, officers may search containers."
    mentions = extract_citation_mentions(text)

    assert len(mentions) >= 2
    normalized = {m.normalized_text for m in mentions}
    assert "267 U.S. 132" in normalized
    assert "456 U.S. 798" in normalized

    for mention in mentions:
        assert mention.start_char >= 0
        assert mention.end_char > mention.start_char
        assert text[mention.start_char:mention.end_char].strip()
