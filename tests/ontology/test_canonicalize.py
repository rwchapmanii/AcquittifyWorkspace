from acquittify.ontology.canonicalize import canonicalize_issues
from acquittify.ontology.extractor import ExtractedIssue
from acquittify.ontology.schemas import IssueNode



def test_canonicalize_matches_existing_issue_by_citation_root() -> None:
    existing = [
        IssueNode(
            issue_id="issue.4a.auto_exception.applicability",
            normalized_form="Whether the automobile exception applies.",
            taxonomy={"domain": "Fourth Amendment", "doctrine": "Automobile Exception", "rule_type": "Exception Applicability"},
            anchors={"canonical_citations": ["courtlistener.123"]},
            dimensions={"required_fact_dimensions": []},
            linked_holdings=[],
            metrics={},
        )
    ]

    extracted = [
        ExtractedIssue(
            normalized_form="Whether the automobile exception applies when the car is mobile.",
            taxonomy={"domain": "Fourth Amendment", "doctrine": "Automobile Exception", "rule_type": "Exception Applicability"},
            supporting_citations=["267 U.S. 132"],
        )
    ]

    outcome = canonicalize_issues(
        extracted_issues=extracted,
        citation_case_map={"267 U.S. 132": "courtlistener.123"},
        existing_issues=existing,
        default_linked_holdings=["us.scotus.1925.carroll.H1"],
    )

    assert len(outcome.issues) == 1
    assert outcome.decisions[0].created is False
    assert outcome.issues[0].issue_id == "issue.4a.auto_exception.applicability"
    assert "us.scotus.1925.carroll.H1" in outcome.issues[0].linked_holdings



def test_canonicalize_rejects_low_signal_issue() -> None:
    extracted = [
        ExtractedIssue(
            normalized_form="Vehicle details",
            taxonomy={"domain": "", "doctrine": "", "rule_type": ""},
            supporting_citations=[],
        )
    ]

    outcome = canonicalize_issues(
        extracted_issues=extracted,
        citation_case_map={},
        existing_issues=[],
    )

    assert len(outcome.issues) == 0
    assert len(outcome.unresolved) == 1
    assert outcome.unresolved[0]["reason"] == "minimality_reject"


def test_canonicalize_prefers_controlling_citation_anchor() -> None:
    existing = [
        IssueNode(
            issue_id="issue.4a.auto_exception.applicability",
            normalized_form="Whether the automobile exception applies.",
            taxonomy={"domain": "Fourth Amendment", "doctrine": "Automobile Exception", "rule_type": "Exception Applicability"},
            anchors={"canonical_citations": ["courtlistener.carroll"]},
            dimensions={"required_fact_dimensions": []},
            linked_holdings=[],
            metrics={},
        )
    ]

    extracted = [
        ExtractedIssue(
            normalized_form="Whether the automobile exception applies when probable cause exists.",
            taxonomy={"domain": "Fourth Amendment", "doctrine": "Automobile Exception", "rule_type": "Exception Applicability"},
            supporting_citations=["267 U.S. 132", "526 U.S. 295"],
        )
    ]

    outcome = canonicalize_issues(
        extracted_issues=extracted,
        citation_case_map={"267 U.S. 132": "courtlistener.carroll", "526 U.S. 295": "courtlistener.other"},
        existing_issues=existing,
        citation_role_map={"267 U.S. 132": "controlling", "526 U.S. 295": "background"},
    )

    assert len(outcome.issues) == 1
    assert outcome.decisions[0].created is False
    assert outcome.issues[0].issue_id == "issue.4a.auto_exception.applicability"


def test_canonicalize_dimension_first_attaches_fact_variant() -> None:
    existing = [
        IssueNode(
            issue_id="issue.fourth_amendment.automobile_exception.exception_applicability",
            normalized_form="Whether the automobile exception applies.",
            taxonomy={"domain": "Fourth Amendment", "doctrine": "Automobile Exception", "rule_type": "Exception Applicability"},
            anchors={"canonical_citations": ["courtlistener.carroll"]},
            dimensions={"required_fact_dimensions": ["vehicle_status"]},
            linked_holdings=[],
            metrics={},
        )
    ]

    extracted = [
        ExtractedIssue(
            normalized_form="Whether the automobile exception applies when the vehicle is impounded at station house.",
            taxonomy={"domain": "Fourth Amendment", "doctrine": "Automobile Exception", "rule_type": ""},
            required_fact_dimensions=[],
            supporting_citations=[],
        )
    ]

    outcome = canonicalize_issues(
        extracted_issues=extracted,
        citation_case_map={},
        existing_issues=existing,
        default_linked_holdings=["us.ca9.2001.foo.H1"],
    )

    assert len(outcome.issues) == 1
    assert outcome.decisions[0].created is False
    assert "dimension" in outcome.decisions[0].reason
    assert "custody_status" in outcome.issues[0].dimensions["required_fact_dimensions"]
    assert "us.ca9.2001.foo.H1" in outcome.issues[0].linked_holdings


def test_canonicalize_creates_new_issue_when_rule_logic_differs() -> None:
    existing = [
        IssueNode(
            issue_id="issue.fourth_amendment.automobile_exception.exception_applicability",
            normalized_form="Whether the automobile exception applies.",
            taxonomy={"domain": "Fourth Amendment", "doctrine": "Automobile Exception", "rule_type": "Exception Applicability"},
            anchors={"canonical_citations": []},
            dimensions={"required_fact_dimensions": []},
            linked_holdings=[],
            metrics={},
        )
    ]

    extracted = [
        ExtractedIssue(
            normalized_form="Whether the automobile exception extends to containers in trunk.",
            taxonomy={"domain": "Fourth Amendment", "doctrine": "Automobile Exception", "rule_type": "Container Scope"},
            required_fact_dimensions=["container_status"],
            supporting_citations=[],
        )
    ]

    outcome = canonicalize_issues(
        extracted_issues=extracted,
        citation_case_map={},
        existing_issues=existing,
    )

    assert len(outcome.issues) == 2
    assert outcome.decisions[0].created is True
