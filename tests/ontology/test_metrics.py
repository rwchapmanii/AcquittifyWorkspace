from pathlib import Path

from acquittify.ontology.metrics import apply_metrics, load_params
from acquittify.ontology.schemas import (
    CitationType,
    HoldingNode,
    IssueNode,
    RelationNode,
    RelationType,
)


def _holding(holding_id: str, base_weight: float, case_id: str = "us.scotus.1925.carroll.267us132") -> HoldingNode:
    return HoldingNode(
        holding_id=holding_id,
        case_id=case_id,
        normative_source=["constitution.us.amendment.4"],
        holding_text="Test holding",
        if_condition=[],
        then_consequence=[],
        normative_strength="binding_core",
        standard_of_review=None,
        burden={"party": None, "level": None},
        fact_vector=[],
        authority={"base_weight": base_weight, "modifiers": {}, "final_weight": base_weight},
        anchors={"doctrinal_root": {"root_case_id": case_id, "root_holding_id": holding_id}},
        citations_supporting=[],
        metrics={},
    )


def _issue(linked_holdings: list[str]) -> IssueNode:
    return IssueNode(
        issue_id="issue.4a.auto_exception.applicability",
        normalized_form="Whether exception applies",
        taxonomy={"domain": "Fourth Amendment", "doctrine": "Automobile Exception", "rule_type": "Applicability"},
        anchors={"canonical_citations": []},
        dimensions={"required_fact_dimensions": []},
        linked_holdings=linked_holdings,
        metrics={},
    )


def _relation(relation_id: str, source: str, target: str, relation_type: RelationType, confidence: float) -> RelationNode:
    return RelationNode(
        relation_id=relation_id,
        source_holding_id=source,
        target_holding_id=target,
        relation_type=relation_type,
        citation_type=CitationType.controlling,
        confidence=confidence,
        weight_modifier=1.0,
        evidence_span={"start_char": 0, "end_char": 1, "quote": "x"},
    )


def test_apply_metrics_updates_holdings_and_issues() -> None:
    holdings = [
        _holding("h1", 1.0),
        _holding("h2", 0.8),
    ]
    issues = [_issue(["h1", "h2"])]
    relations = [
        _relation("r1", "h2", "h1", RelationType.overrules, 0.9),
        _relation("r2", "h2", "h1", RelationType.clarifies, 0.8),
    ]

    params = load_params(None)
    bundle = apply_metrics(holdings=holdings, issues=issues, relations=relations, params=params)

    assert "h1" in bundle.holding_scores
    assert "h2" in bundle.holding_scores
    assert holdings[0].metrics.get("PF_holding") == bundle.holding_scores["h1"]
    assert issues[0].metrics.get("PF_issue") == bundle.issue_scores[issues[0].issue_id]["PF_issue"]
    assert len(bundle.interpretation_events) == 2


def test_circuit_split_lowers_consensus_and_raises_drift() -> None:
    holding_defs = [
        ("us.ca1.2010.alpha.H1", "us.ca1.2010.alpha.100f3d1"),
        ("us.ca2.2011.beta.H1", "us.ca2.2011.beta.200f3d2"),
        ("us.ca3.2012.gamma.H1", "us.ca3.2012.gamma.300f3d3"),
    ]

    def _scenario(relations: list[RelationNode]) -> dict:
        holdings = [_holding(holding_id, 1.0, case_id=case_id) for holding_id, case_id in holding_defs]
        issues = [_issue([holding_id for holding_id, _ in holding_defs])]
        params = load_params(None)
        bundle = apply_metrics(holdings=holdings, issues=issues, relations=relations, params=params)
        return bundle.issue_scores[issues[0].issue_id]

    split = _scenario(
        [
            _relation("s1", "us.ca1.2010.alpha.H1", "us.ca1.2010.alpha.H1", RelationType.applies, 1.0),
            _relation("s2", "us.ca2.2011.beta.H1", "us.ca1.2010.alpha.H1", RelationType.limits, 1.0),
            _relation("s3", "us.ca3.2012.gamma.H1", "us.ca1.2010.alpha.H1", RelationType.extends, 1.0),
        ]
    )
    unanimous = _scenario(
        [
            _relation("u1", "us.ca1.2010.alpha.H1", "us.ca1.2010.alpha.H1", RelationType.applies, 1.0),
            _relation("u2", "us.ca2.2011.beta.H1", "us.ca1.2010.alpha.H1", RelationType.clarifies, 1.0),
            _relation("u3", "us.ca3.2012.gamma.H1", "us.ca1.2010.alpha.H1", RelationType.extends, 1.0),
        ]
    )

    assert split["active_circuits"] == 3
    assert unanimous["active_circuits"] == 3
    assert split["consensus"] < unanimous["consensus"]
    assert split["drift"] > unanimous["drift"]


def test_secondary_source_weight_reduces_holding_pf() -> None:
    holdings = [
        _holding("h_const", 1.0),
        _holding("h_sec", 1.0),
    ]

    # Attach source links directly to isolate source-weight impact.
    p0 = holdings[0].model_dump() if hasattr(holdings[0], "model_dump") else holdings[0].dict()
    p1 = holdings[1].model_dump() if hasattr(holdings[1], "model_dump") else holdings[1].dict()
    p0["source_links"] = [{"source_id": "constitution.us.amendment.4", "weight": 1.0}]
    p1["source_links"] = [{"source_id": "secondary.hornbook.lafave.crimpro.6e", "weight": 0.3}]
    holdings[0] = HoldingNode(**p0)
    holdings[1] = HoldingNode(**p1)

    issues = [_issue(["h_const", "h_sec"])]
    bundle = apply_metrics(holdings=holdings, issues=issues, relations=[], params=load_params(None))

    assert bundle.holding_scores["h_const"] > bundle.holding_scores["h_sec"]
    assert bundle.holding_scores["h_sec"] == 0.3


def test_load_params_supports_yaml_override(tmp_path: Path) -> None:
    custom = tmp_path / "params.yaml"
    custom.write_text(
        """
relation_effects:
  overrules: -0.5
issue_adjustments:
  drift_delta: 0.2
""".strip()
        + "\n",
        encoding="utf-8",
    )

    params = load_params(custom)
    assert params["relation_effects"]["overrules"] == -0.5
    assert params["issue_adjustments"]["drift_delta"] == 0.2
    assert params["relation_effects"]["applies"] == 0.06
