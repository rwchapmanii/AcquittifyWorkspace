from acquittify.ontology.citation_extract import extract_citation_mentions
from acquittify.ontology.citation_roles import classify_citation_roles
from acquittify.ontology.schemas import CitationRole



def _first_role(text: str) -> CitationRole:
    mentions = extract_citation_mentions(text)
    assignments = classify_citation_roles(text, mentions)
    assert assignments
    return assignments[0].role



def test_classify_controlling_role() -> None:
    text = "Under Carroll, 267 U.S. 132, we hold the search lawful."
    assert _first_role(text) == CitationRole.controlling



def test_classify_background_role() -> None:
    text = "See also Carroll, 267 U.S. 132, for historical context."
    assert _first_role(text) == CitationRole.background



def test_classify_persuasive_role() -> None:
    text = "The panel found Carroll, 267 U.S. 132, persuasive but not binding here."
    assert _first_role(text) == CitationRole.persuasive
