import pytest

from acquittify.ontology.extractor import ExtractionValidationError, parse_extraction_json



def test_parse_extraction_json_accepts_valid_payload() -> None:
    payload = """
    {
      "holdings": [
        {
          "holding_text": "If probable cause exists for a vehicle, a warrantless search is permitted.",
          "if_condition": [{"predicate": "probable_cause", "value": true}],
          "then_consequence": [{"predicate": "warrantless_search_permitted", "value": true}],
          "normative_strength": "binding_core",
          "normative_source": ["constitution.us.amendment.4", "secondary.hornbook.lafave.crimpro.6e"],
          "fact_vector": [{"dimension": "vehicle_mobility", "value": "inherent"}],
          "secondary_sources": [{"source_id": "secondary.hornbook.lafave.crimpro.6e", "title": "LaFave", "topic_tags": ["Fourth Amendment"]}],
          "citations_supporting": ["us.scotus.1925.carroll.267us132"]
        }
      ],
      "issues": [
        {
          "normalized_form": "Whether the automobile exception applies.",
          "taxonomy": {"domain": "Fourth Amendment", "doctrine": "Automobile Exception", "rule_type": "Exception Applicability"},
          "required_fact_dimensions": ["vehicle_status"],
          "supporting_citations": ["us.scotus.1925.carroll.267us132"]
        }
      ],
      "relations": [
        {
          "source_holding_index": 0,
          "target_holding_index": 0,
          "relation_type": "clarifies",
          "citation_type": "controlling",
          "confidence": 0.82,
          "evidence_span": {"start_char": 10, "end_char": 35}
        }
      ]
    }
    """

    parsed = parse_extraction_json(payload)
    assert len(parsed.holdings) == 1
    assert "secondary.hornbook.lafave.crimpro.6e" in parsed.holdings[0].normative_source
    assert parsed.holdings[0].fact_vector[0].dimension == "vehicle_mobility"
    assert parsed.holdings[0].secondary_sources[0].title == "LaFave"
    assert parsed.issues[0].required_fact_dimensions == ["vehicle_status"]
    assert parsed.relations[0].confidence == 0.82


def test_parse_extraction_json_accepts_optional_relation_holding_ids() -> None:
    payload = """
    {
      "holdings": [],
      "issues": [],
      "relations": [
        {
          "source_holding_index": 0,
          "target_holding_id": "us.scotus.1925.carroll.H1",
          "relation_type": "extends",
          "citation_type": "controlling",
          "confidence": 0.8,
          "evidence_span": {"start_char": 0, "end_char": 10}
        }
      ]
    }
    """
    parsed = parse_extraction_json(payload)
    assert parsed.relations[0].target_holding_id == "us.scotus.1925.carroll.H1"



def test_parse_extraction_json_rejects_invalid_relation_type() -> None:
    payload = """
    {
      "holdings": [],
      "issues": [],
      "relations": [
        {
          "source_holding_index": 0,
          "target_holding_index": 0,
          "relation_type": "invalid_relation",
          "citation_type": "controlling",
          "confidence": 0.9,
          "evidence_span": {"start_char": 0, "end_char": 2}
        }
      ]
    }
    """

    with pytest.raises(ExtractionValidationError):
        parse_extraction_json(payload)


def test_parse_extraction_json_accepts_markdown_fenced_json() -> None:
    payload = """
Here is the structured output:
```json
{
  "holdings": [],
  "issues": [],
  "relations": []
}
```
"""
    parsed = parse_extraction_json(payload)
    assert parsed.holdings == []
    assert parsed.issues == []
    assert parsed.relations == []


def test_parse_extraction_json_clamps_relation_confidence() -> None:
    payload = """
    {
      "holdings": [],
      "issues": [],
      "relations": [
        {
          "relation_type": "clarifies",
          "citation_type": "controlling",
          "confidence": 2,
          "evidence_span": {"start_char": 5, "end_char": 1}
        }
      ]
    }
    """
    parsed = parse_extraction_json(payload)
    assert parsed.relations[0].confidence == 1.0
    assert parsed.relations[0].evidence_span["start_char"] == 5
    assert parsed.relations[0].evidence_span["end_char"] == 5


def test_parse_extraction_json_accepts_interpretive_edges_alias() -> None:
    payload = """
    {
      "edges": [
        {
          "source_case": "United States v. Example",
          "target_authority": "U.S. Const. amend. IV",
          "authority_type": "CONSTITUTION",
          "edge_type": "APPLIES_AMENDMENT",
          "confidence": 0.92,
          "text_span": "Under the Fourth Amendment, this search was unreasonable."
        },
        {
          "source_case": "United States v. Example",
          "target_authority": "18 U.S.C. § 922(g)(1)",
          "authority_type": "STATUTE",
          "edge_type": "INTERPRETS_STATUTE",
          "confidence": 0.88,
          "text_span": "We interpret § 922(g)(1) to require knowing status."
        }
      ]
    }
    """
    parsed = parse_extraction_json(payload)
    assert parsed.holdings == []
    assert parsed.issues == []
    assert parsed.relations == []
    assert len(parsed.interpretive_edges) == 2
    assert parsed.interpretive_edges[0].edge_type == "APPLIES_AMENDMENT"
    assert parsed.interpretive_edges[1].authority_type == "STATUTE"
