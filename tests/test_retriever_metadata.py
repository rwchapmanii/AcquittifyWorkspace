from acquittify_retriever import _build_result_doc


def test_build_result_doc_passes_authority_metadata():
    meta = {
        "source_type": "case",
        "title": "United States v. Example",
        "path": "/tmp/example.txt",
        "chunk_index": 3,
        "doc_id": "doc-123",
        "source_id": "cl-456",
        "court": "SCOTUS",
        "circuit": "2d",
        "year": 2020,
        "posture": "APPEAL",
        "taxonomy": "FCD.ISS.DISCOVERY.BRADY",
        "taxonomy_version": "FCD-1.0",
        "is_holding": True,
        "is_dicta": False,
        "standard_of_review": "de novo",
        "burden": "preponderance",
        "favorability": 1,
        "citations": ["507 U.S. 170"],
        "statutes": ["18 U.S.C. § 1962"],
        "rules": ["Fed. R. Crim. P. 16"],
        "citation_count": 1,
        "statute_count": 1,
        "rule_count": 1,
    }
    result = _build_result_doc("text", meta, 0.42, "id-1")
    assert result["doc_id"] == "doc-123"
    assert result["source_id"] == "cl-456"
    assert result["court"] == "SCOTUS"
    assert result["circuit"] == "2d"
    assert result["year"] == 2020
    assert result["posture"] == "APPEAL"
    assert result["citations"] == ["507 U.S. 170"]
    assert result["statutes"] == ["18 U.S.C. § 1962"]
    assert result["rules"] == ["Fed. R. Crim. P. 16"]
