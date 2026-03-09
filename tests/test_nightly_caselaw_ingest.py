from __future__ import annotations

import uuid

from scripts import nightly_caselaw_ingest as ingest


def test_order_federal_courts_prioritizes_scotus_then_cafc() -> None:
    ordered = ingest.order_federal_courts(["cadc", "cafc", "scotus", "ca2", "ca2", "cadc"])
    assert ordered[:2] == ["scotus", "cafc"]
    assert ordered == ["scotus", "cafc", "ca2", "cadc"]


def test_is_federal_court_record() -> None:
    assert ingest.is_federal_court_record(
        {
            "id": "scotus",
            "jurisdiction": "F",
            "in_use": True,
            "has_opinion_scraper": True,
        }
    )
    assert not ingest.is_federal_court_record(
        {
            "id": "colo",
            "jurisdiction": "S",
            "in_use": True,
            "has_opinion_scraper": True,
        }
    )


def test_classify_case_type_criminal() -> None:
    case_type, reason = ingest.classify_case_type(
        case_name="United States v. Doe",
        docket_number="23-1234",
        citations=["18 U.S.C. 922(g)"],
        opinion_text="Defendant was indicted and convicted. The district court imposed sentence.",
    )
    assert case_type == "criminal"
    assert "pattern" in reason


def test_classify_case_type_quasi_criminal() -> None:
    case_type, _ = ingest.classify_case_type(
        case_name="Smith v. United States",
        docket_number="22-100",
        citations=[],
        opinion_text="Petitioner seeks relief under 28 U.S.C. 2255 from conviction.",
    )
    assert case_type == "quasi_criminal"


def test_classify_case_type_non_criminal() -> None:
    case_type, _ = ingest.classify_case_type(
        case_name="Acme Corp. v. City",
        docket_number="24-42",
        citations=["42 U.S.C. 1983"],
        opinion_text="This appeal concerns civil liability and contract interpretation.",
    )
    assert case_type == "non_criminal"


def test_fallback_taxonomy_entries_returns_known_code() -> None:
    catalog = {
        "5A.MIR.GEN.GEN": "Miranda general",
        "PROC.MOT.DISMISS.GENERAL": "Motion to dismiss general",
    }
    entries = ingest.fallback_taxonomy_entries("Miranda warning was disputed.", catalog)
    assert entries
    assert entries[0]["code"] == "5A.MIR.GEN.GEN"


def test_build_case_frontmatter_contains_taxonomy_and_sources() -> None:
    frontmatter = ingest.build_case_frontmatter(
        cluster_id=123,
        opinion_id=456,
        case_name="United States v. Example",
        court_id="cafc",
        court_name="Court of Appeals for the Federal Circuit",
        date_filed="2026-03-06",
        docket_number="24-1010",
        citations=["123 F.4th 1"],
        case_type="criminal",
        taxonomy_entries=[{"code": "SENT.GUIDE.GEN.GEN", "label": "Sentencing guidelines general"}],
        taxonomy_version="2026.01",
        opinion_text="The panel reviewed the sentence imposed below.",
        publication_status="Published",
        opinion_type="majority",
        absolute_url="https://www.courtlistener.com/opinion/123/",
        reason="matched criminal pattern",
    )

    assert frontmatter["case_id"] == "case.courtlistener.cluster.123"
    assert frontmatter["case_taxonomies"][0]["code"] == "SENT.GUIDE.GEN.GEN"
    assert frontmatter["sources"]["courtlistener_cluster_id"] == 123
    assert frontmatter["sources"]["courtlistener_opinion_id"] == 456


def test_taxonomy_entries_from_frontmatter_supports_mixed_types() -> None:
    frontmatter = {
        "case_taxonomies": [
            {"code": "SENT.GUIDE.GEN.GEN", "label": "Sentencing guidelines general"},
            "PROC.MOT.DISMISS.GENERAL",
            {"code": "SENT.GUIDE.GEN.GEN"},
        ]
    }
    catalog = {"PROC.MOT.DISMISS.GENERAL": "Motion to dismiss"}
    entries = ingest.taxonomy_entries_from_frontmatter(frontmatter, catalog)
    assert entries == [
        {"code": "SENT.GUIDE.GEN.GEN", "label": "Sentencing guidelines general"},
        {"code": "PROC.MOT.DISMISS.GENERAL", "label": "Motion to dismiss"},
    ]


def test_build_legal_unit_payloads_emits_deterministic_units() -> None:
    units = ingest.build_legal_unit_payloads(
        case_id="case.courtlistener.cluster.999",
        taxonomy_codes=["SENT.GUIDE.GEN.GEN", "PROC.MOT.DISMISS.GENERAL"],
        taxonomy_version="2026.01",
        court_id="scotus",
        court_name="Supreme Court of the United States",
        date_filed="2026-03-07",
        frontmatter={"title": "United States v. Example", "essential_holding": "Holding text"},
        opinion_text="Body text",
        source_opinion_id=999,
        ingestion_batch_id="nightly_caselaw:20260307T000000Z",
    )
    assert len(units) == 2
    assert all(isinstance(unit["unit_id"], uuid.UUID) for unit in units)
    assert all(unit["taxonomy_version"] == "2026.01" for unit in units)
    assert all(unit["source_opinion_id"] == 999 for unit in units)
    assert units[0]["authority_weight"] == 100


def test_normalize_case_date_rejects_year_zero() -> None:
    assert ingest.normalize_case_date("0000") == "1900-01-01"
