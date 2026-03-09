from pathlib import Path

from acquittify.ontology.schemas import (
    CaseNode,
    CitationType,
    HoldingNode,
    IssueNode,
    RelationNode,
    RelationType,
    SecondaryNode,
    SourceNode,
    SourceType,
)
from acquittify.ontology.vault_writer import VaultWriter



def _make_case() -> CaseNode:
    return CaseNode(
        case_id="us.scotus.1925.carroll.267us132",
        title="Carroll v. United States",
        court="SCOTUS",
        court_level="supreme",
        jurisdiction="US",
        date_decided="1925-03-02",
        publication_status="published",
        opinion_type="majority",
        judges={"author": "", "joining": []},
        citations_in_text=["267 U.S. 132"],
        sources={"opinion_text_source": "test", "opinion_url": ""},
    )



def _make_holding() -> HoldingNode:
    return HoldingNode(
        holding_id="us.scotus.1925.carroll.H1",
        case_id="us.scotus.1925.carroll.267us132",
        normative_source=["constitution.us.amendment.4"],
        holding_text="Warrantless search is permitted with probable cause.",
        if_condition=[{"predicate": "probable_cause", "value": True}],
        then_consequence=[{"predicate": "warrantless_search_permitted", "value": True}],
        normative_strength="binding_core",
        standard_of_review=None,
        burden={"party": None, "level": None},
        fact_vector=[],
        authority={"base_weight": 1.0, "modifiers": {}, "final_weight": 1.0},
        anchors={"doctrinal_root": {"root_case_id": "us.scotus.1925.carroll.267us132", "root_holding_id": "us.scotus.1925.carroll.H1"}},
        citations_supporting=["courtlistener.123"],
    )



def _make_issue() -> IssueNode:
    return IssueNode(
        issue_id="issue.4a.auto_exception.applicability",
        normalized_form="Whether the automobile exception applies.",
        taxonomy={"domain": "Fourth Amendment", "doctrine": "Automobile Exception", "rule_type": "Exception Applicability"},
        anchors={"canonical_citations": ["courtlistener.123"]},
        dimensions={"required_fact_dimensions": []},
        linked_holdings=["us.scotus.1925.carroll.H1"],
        metrics={"PF_issue": None},
    )



def _make_relation() -> RelationNode:
    return RelationNode(
        relation_id="rel.us.scotus.1991.acevedo.H1__clarifies__us.scotus.1925.carroll.H1",
        source_holding_id="us.scotus.1991.acevedo.H1",
        target_holding_id="us.scotus.1925.carroll.H1",
        relation_type=RelationType.clarifies,
        citation_type=CitationType.controlling,
        confidence=0.82,
        weight_modifier=0.7,
        evidence_span={"start_char": 10, "end_char": 20, "quote": "clarifies earlier rule"},
    )


def _make_sources() -> list[SourceNode | SecondaryNode]:
    return [
        SourceNode(
            source_id="constitution.us.amendment.4",
            source_type=SourceType.constitution,
            title=None,
            authority_weight=1.0,
            topic_tags=[],
        ),
        SecondaryNode(
            source_id="secondary.hornbook.lafave.crimpro.6e",
            title="LaFave, Criminal Procedure (6th ed.)",
            authority_weight=0.3,
            topic_tags=["Fourth Amendment"],
        ),
    ]



def test_writer_is_idempotent(tmp_path: Path) -> None:
    writer = VaultWriter(vault_root=tmp_path)

    case = _make_case()
    holding = _make_holding()
    issue = _make_issue()
    relation = _make_relation()

    first = writer.write_all(
        case_node=case,
        holding_nodes=[holding],
        issue_nodes=[issue],
        relation_nodes=[relation],
        source_nodes=_make_sources(),
        unresolved_items=[],
        params={"relation_effects": {"clarifies": 0.7}},
        metrics_payload={"PF_holding": {"us.scotus.1925.carroll.H1": 1.0}},
        interpretation_events=[],
    )
    second = writer.write_all(
        case_node=case,
        holding_nodes=[holding],
        issue_nodes=[issue],
        relation_nodes=[relation],
        source_nodes=_make_sources(),
        unresolved_items=[],
        params={"relation_effects": {"clarifies": 0.7}},
        metrics_payload={"PF_holding": {"us.scotus.1925.carroll.H1": 1.0}},
        interpretation_events=[],
    )

    assert first["changed_count"] > 0
    assert second["changed_count"] == 0
    assert (tmp_path / "indices" / "unresolved_queue.md").exists()
    assert (tmp_path / "indices" / "review_checklist.md").exists()
    assert (tmp_path / "indices" / "params.yaml").exists()
    assert (tmp_path / "indices" / "metrics.yaml").exists()
    assert (tmp_path / "sources" / "constitution" / "constitution.us.amendment.4.md").exists()
    assert (tmp_path / "sources" / "secondary" / "secondary.hornbook.lafave.crimpro.6e.md").exists()


def test_load_existing_holding_ids(tmp_path: Path) -> None:
    writer = VaultWriter(vault_root=tmp_path)
    case = _make_case()
    holding = _make_holding()

    writer.write_all(
        case_node=case,
        holding_nodes=[holding],
        issue_nodes=[_make_issue()],
        relation_nodes=[],
        source_nodes=[],
        unresolved_items=[],
        params=None,
        metrics_payload=None,
        interpretation_events=[],
    )

    existing = writer.load_existing_holding_ids()
    assert "us.scotus.1925.carroll.H1" in existing


def test_load_existing_case_citation_map(tmp_path: Path) -> None:
    writer = VaultWriter(vault_root=tmp_path)
    case = _make_case()
    case.sources["primary_citation"] = "267 U.S. 132"

    writer.write_all(
        case_node=case,
        holding_nodes=[_make_holding()],
        issue_nodes=[_make_issue()],
        relation_nodes=[],
        source_nodes=[],
        unresolved_items=[],
        params=None,
        metrics_payload=None,
        interpretation_events=[],
    )

    mapping = writer.load_existing_case_citation_map()
    assert mapping["267 U.S. 132"] == "us.scotus.1925.carroll.267us132"
