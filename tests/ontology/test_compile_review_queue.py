import json
import os
from pathlib import Path
import subprocess
import sys


def test_compile_enriches_unresolved_review_fields(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts" / "compile_precedent_ontology.py"

    text_path = tmp_path / "opinion.txt"
    text_path.write_text(
        "The court discusses background and references automobile doctrine without resolving it.",
        encoding="utf-8",
    )

    extraction = {
        "holdings": [
            {
                "holding_text": "If probable cause exists, warrantless search is permitted.",
                "if_condition": [{"predicate": "probable_cause", "value": True}],
                "then_consequence": [{"predicate": "warrantless_search_permitted", "value": True}],
                "normative_strength": "binding_core",
                "citations_supporting": [],
            }
        ],
        "issues": [
            {
                "normalized_form": "Background facts from the stop.",
                "taxonomy": {},
                "required_fact_dimensions": [],
                "supporting_citations": [],
            }
        ],
        "relations": [
            {
                "source_holding_index": 0,
                "target_holding_index": 7,
                "relation_type": "clarifies",
                "citation_type": "controlling",
                "confidence": 0.7,
                "evidence_span": {"start_char": 0, "end_char": 20},
            }
        ],
    }

    extraction_path = tmp_path / "extract.json"
    extraction_path.write_text(json.dumps(extraction), encoding="utf-8")
    vault_root = tmp_path / "vault"
    out_path = tmp_path / "out.json"

    cmd = [
        sys.executable,
        str(script),
        "--text-file",
        str(text_path),
        "--extraction-json",
        str(extraction_path),
        "--skip-resolver",
        "--vault-root",
        str(vault_root),
        "--title",
        "Example Case",
        "--court",
        "CA9",
        "--court-level",
        "circuit",
        "--jurisdiction",
        "US",
        "--date-decided",
        "2010-01-01",
        "--primary-citation",
        "600 F.3d 100",
        "--output",
        str(out_path),
    ]

    env = dict(os.environ)
    env.update({"PYTHONPATH": str(root)})
    subprocess.run(cmd, check=True, cwd=str(root), env=env)

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["unresolved_count"] == 2
    assert payload["unresolved_by_severity"]["total"] == 2
    assert payload["metrics_explainability"]["holdings"]

    for item in payload["unresolved_items"]:
        assert item["review_id"].startswith("review.")
        assert item["category"]
        assert item["severity"] in {"critical", "high", "medium", "low"}
        assert item["review_action"]
        assert item["status"] == "open"

    queue_text = (vault_root / "indices" / "unresolved_queue.md").read_text(encoding="utf-8")
    checklist_text = (vault_root / "indices" / "review_checklist.md").read_text(encoding="utf-8")
    assert "Review Checklist" in checklist_text
    assert "Queue Snapshot" in checklist_text
    assert "review.issue_unresolved." in queue_text
    assert "review.relation_unresolved." in queue_text
