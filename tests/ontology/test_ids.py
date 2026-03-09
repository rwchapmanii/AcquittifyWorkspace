from acquittify.ontology.ids import (
    build_case_id,
    build_holding_id,
    build_issue_id,
    case_note_filename,
    holding_note_filename,
    issue_note_filename,
)


def test_case_id_is_deterministic() -> None:
    case_id_a = build_case_id(
        jurisdiction="US",
        court="SCOTUS",
        date_decided="1925-03-02",
        title="Carroll v. United States",
        primary_citation="267 U.S. 132",
    )
    case_id_b = build_case_id(
        jurisdiction="US",
        court="SCOTUS",
        date_decided="1925-03-02",
        title="Carroll v. United States",
        primary_citation="267 U.S. 132",
    )

    assert case_id_a == case_id_b
    assert case_id_a == "us.scotus.1925.carroll.267us132"


def test_note_filenames_match_convention() -> None:
    case_id = "us.scotus.1925.carroll.267us132"
    assert case_note_filename(case_id, "267 U.S. 132") == "case__us__scotus__1925__carroll__267_us_132.md"
    assert holding_note_filename(case_id, 1) == "holding__carroll__H1.md"



def test_issue_ids_and_filenames() -> None:
    issue_id = build_issue_id("4A", "Automobile Exception", "Applicability")
    assert issue_id == "issue.4a.automobile_exception.applicability"
    assert issue_note_filename(issue_id) == "issue__4a__automobile_exception__applicability.md"



def test_holding_id() -> None:
    assert build_holding_id("us.scotus.1925.carroll.267us132", 2) == "us.scotus.1925.carroll.H2"
