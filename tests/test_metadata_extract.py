from acquittify.metadata_extract import extract_citation_data
from acquittify.authority import compute_authority_weight


def test_extract_citation_data():
    text = "See 18 U.S.C. § 1962 and Reves, 507 U.S. 170 (1993). Fed. R. Crim. P. 16."
    data = extract_citation_data(text)
    assert data["statute_count"] >= 1
    assert data["rule_count"] >= 1
    assert data["citation_count"] >= 1


def test_compute_authority_weight():
    meta = {"court": "scotus", "source_type": "Supreme Court"}
    weight = compute_authority_weight(meta, "507 U.S. 170")
    assert weight >= 5
