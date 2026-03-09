from acquittify.ontology.extractor import ExtractedRelation
from acquittify.ontology.relations import build_relation_nodes
from acquittify.ontology.schemas import CitationType, RelationType



def test_relation_high_signal_overrules() -> None:
    text = "The Court expressly overruled the prior case in this section."
    extracted = [
        ExtractedRelation(
            source_holding_index=0,
            target_holding_index=1,
            relation_type=RelationType.clarifies,
            citation_type=CitationType.controlling,
            confidence=0.62,
            evidence_span={"start_char": 20, "end_char": 40},
        )
    ]

    result = build_relation_nodes(
        extracted_relations=extracted,
        holding_ids=["a.H1", "b.H1"],
        opinion_text=text,
    )

    assert len(result.relations) == 1
    assert result.relations[0].relation_type == RelationType.overrules
    assert result.relations[0].weight_modifier == 0.1



def test_relation_index_out_of_range_is_unresolved() -> None:
    text = "No relation text."
    extracted = [
        ExtractedRelation(
            source_holding_index=0,
            target_holding_index=2,
            relation_type=RelationType.clarifies,
            citation_type=CitationType.controlling,
            confidence=0.5,
            evidence_span={"start_char": 0, "end_char": 2},
        )
    ]

    result = build_relation_nodes(
        extracted_relations=extracted,
        holding_ids=["a.H1"],
        opinion_text=text,
    )

    assert len(result.relations) == 0
    assert len(result.unresolved) == 1
    assert result.unresolved[0]["reason"] == "holding_index_out_of_range"


def test_relation_supports_cross_case_target_holding_id() -> None:
    text = "This opinion clarifies the prior rule."
    extracted = [
        ExtractedRelation(
            source_holding_index=0,
            target_holding_id="us.scotus.1925.carroll.H1",
            relation_type=RelationType.clarifies,
            citation_type=CitationType.controlling,
            confidence=0.77,
            evidence_span={"start_char": 0, "end_char": 10},
        )
    ]

    result = build_relation_nodes(
        extracted_relations=extracted,
        holding_ids=["us.scotus.1982.ross.H1"],
        opinion_text=text,
        known_holding_ids={"us.scotus.1925.carroll.H1"},
    )

    assert len(result.relations) == 1
    assert result.relations[0].source_holding_id == "us.scotus.1982.ross.H1"
    assert result.relations[0].target_holding_id == "us.scotus.1925.carroll.H1"


def test_relation_infers_target_holding_from_resolved_citation_context() -> None:
    text = "Ross extends Carroll, 267 U.S. 132, and confirms the rule."
    extracted = [
        ExtractedRelation(
            source_holding_index=0,
            target_holding_index=None,
            relation_type=RelationType.extends,
            citation_type=CitationType.controlling,
            confidence=0.8,
            evidence_span={"start_char": 0, "end_char": 22},
        )
    ]

    result = build_relation_nodes(
        extracted_relations=extracted,
        holding_ids=["us.scotus.1982.ross.H1"],
        opinion_text=text,
        known_holding_ids={"us.scotus.1982.ross.H1", "us.scotus.1925.carroll.H1"},
        citation_mentions=[
            {
                "normalized_text": "267 U.S. 132",
                "start_char": 23,
                "end_char": 35,
                "resolved_case_id": "us.scotus.1925.carroll.267us132",
                "role": "controlling",
            }
        ],
    )

    assert len(result.relations) == 1
    assert result.relations[0].target_holding_id == "us.scotus.1925.carroll.H1"
