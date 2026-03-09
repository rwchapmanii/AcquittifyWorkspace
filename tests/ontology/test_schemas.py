import pytest
from pydantic import ValidationError

from acquittify.ontology.schemas import (
    CaseNode,
    SecondaryNode,
    HoldingNode,
    IssueNode,
    RelationNode,
    RelationType,
    CitationType,
    SourceNode,
    SourceType,
)


def test_case_node_valid() -> None:
    node = CaseNode(
        case_id="us.scotus.1925.carroll.267us132",
        title="Carroll v. United States",
        court="SCOTUS",
        court_level="supreme",
        jurisdiction="US",
        date_decided="1925-03-02",
    )
    assert node.type == "case"
    assert node.case_id.endswith("267us132")


def test_holding_node_valid() -> None:
    node = HoldingNode(
        holding_id="us.scotus.1925.carroll.H1",
        case_id="us.scotus.1925.carroll.267us132",
        normative_source=["constitution.us.amendment.4"],
        holding_text="Warrantless vehicle search is permitted with probable cause.",
        if_condition=[{"predicate": "probable_cause", "value": True}],
        then_consequence=[{"predicate": "warrantless_search_permitted", "value": True}],
    )
    assert node.type == "holding"
    assert node.if_condition[0].predicate == "probable_cause"


def test_issue_node_valid() -> None:
    node = IssueNode(
        issue_id="issue.4a.auto_exception.applicability",
        normalized_form="Whether the automobile exception applies.",
        taxonomy={"domain": "Fourth Amendment", "doctrine": "Automobile Exception"},
    )
    assert node.type == "issue"
    assert node.taxonomy["domain"] == "Fourth Amendment"


def test_relation_confidence_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        RelationNode(
            relation_id="rel.us.scotus.1991.acevedo.H1__clarifies__us.scotus.1925.carroll.H1",
            source_holding_id="us.scotus.1991.acevedo.H1",
            target_holding_id="us.scotus.1925.carroll.H1",
            relation_type=RelationType.clarifies,
            citation_type=CitationType.controlling,
            confidence=1.5,
        )


def test_source_nodes_valid() -> None:
    source = SourceNode(
        source_id="constitution.us.amendment.4",
        source_type=SourceType.constitution,
        authority_weight=1.0,
    )
    secondary = SecondaryNode(
        source_id="secondary.hornbook.lafave.crimpro.6e",
        title="LaFave, Criminal Procedure (6th ed.)",
        authority_weight=0.3,
        topic_tags=["Fourth Amendment"],
    )
    assert source.type == "source"
    assert secondary.type == "secondary"
