import json
import os
from pathlib import Path
import subprocess
import sys



def test_compile_pipeline_idempotent(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts" / "compile_precedent_ontology.py"

    text_path = tmp_path / "opinion.txt"
    text_path.write_text(
        "ON WRIT OF CERTIORARI TO THE UNITED STATES COURT OF APPEALS FOR THE NINTH CIRCUIT. "
        "Under Carroll, 267 U.S. 132, we hold the search valid under 18 U.S.C. § 3553(a)(2)(B). "
        "Agency guidance in 21 C.F.R. § 1306.04(a) confirms the framework. "
        "The Court overruled prior ambiguity.",
        encoding="utf-8",
    )

    extraction = {
        "holdings": [
            {
                "holding_text": "If probable cause exists, warrantless search is permitted.",
                "if_condition": [{"predicate": "probable_cause", "value": True}],
                "then_consequence": [{"predicate": "warrantless_search_permitted", "value": True}],
                "normative_strength": "binding_core",
                "citations_supporting": ["267 U.S. 132"],
            }
        ],
        "issues": [
            {
                "normalized_form": "Whether the automobile exception applies when probable cause exists.",
                "taxonomy": {
                    "domain": "Fourth Amendment",
                    "doctrine": "Automobile Exception",
                    "rule_type": "Exception Applicability",
                },
                "supporting_citations": ["267 U.S. 132"],
            }
        ],
        "relations": [
            {
                "source_holding_index": 0,
                "target_holding_index": 0,
                "relation_type": "clarifies",
                "citation_type": "controlling",
                "confidence": 0.72,
                "evidence_span": {"start_char": 52, "end_char": 83},
            }
        ],
    }
    extraction_path = tmp_path / "extract.json"
    extraction_path.write_text(json.dumps(extraction), encoding="utf-8")

    vault_root = tmp_path / "vault"
    out1 = tmp_path / "run1.json"
    out2 = tmp_path / "run2.json"

    base_cmd = [
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
        "Carroll v. United States",
        "--court",
        "SCOTUS",
        "--court-level",
        "supreme",
        "--jurisdiction",
        "US",
        "--date-decided",
        "1925-03-02",
        "--primary-citation",
        "267 U.S. 132",
    ]

    env = dict(os.environ)
    env.update({"PYTHONPATH": str(root)})

    subprocess.run(base_cmd + ["--output", str(out1)], check=True, cwd=str(root), env=env)
    subprocess.run(base_cmd + ["--output", str(out2)], check=True, cwd=str(root), env=env)

    payload1 = json.loads(out1.read_text(encoding="utf-8"))
    payload2 = json.loads(out2.read_text(encoding="utf-8"))

    assert payload1["write_result"]["changed_count"] > 0
    assert payload2["write_result"]["changed_count"] == 0

    assert (vault_root / "indices" / "params.yaml").exists()
    assert (vault_root / "indices" / "metrics.yaml").exists()
    assert (vault_root / "indices" / "unresolved_queue.md").exists()
    assert (vault_root / "indices" / "review_checklist.md").exists()
    assert payload1["metrics_summary"]["holding_count"] == 1
    assert payload1["metrics_summary"]["issue_count"] == 1
    assert "metrics_explainability" in payload1
    assert payload1["metrics_explainability"]["holdings"]
    assert payload1["unresolved_by_severity"]["total"] == payload1["unresolved_count"]

    case_notes = list((vault_root / "cases").rglob("*.md"))
    assert case_notes
    case_text = case_notes[0].read_text(encoding="utf-8")
    assert 'originating_circuit: "ca9"' in case_text
    assert 'originating_circuit_label: "Ninth Circuit"' in case_text
    assert "authority_anchors:" in case_text

    assert (vault_root / "sources" / "statutes" / "statute.usc.18.md").exists()
    assert (vault_root / "sources" / "regs" / "reg.cfr.21.md").exists()


def test_compile_accepts_interpretive_edges_alias(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts" / "compile_precedent_ontology.py"

    text_path = tmp_path / "opinion.txt"
    text_path.write_text(
        "The Court applies the Fourth Amendment and interprets 18 U.S.C. § 922(g)(1) using plain meaning.",
        encoding="utf-8",
    )

    extraction = {
        "edges": [
            {
                "source_case": "Sample v. Test",
                "target_authority": "U.S. Const. amend. IV",
                "authority_type": "CONSTITUTION",
                "edge_type": "APPLIES_AMENDMENT",
                "confidence": 0.93,
                "text_span": "The Court applies the Fourth Amendment.",
            },
            {
                "source_case": "Sample v. Test",
                "target_authority": "18 U.S.C. § 922(g)(1)",
                "authority_type": "STATUTE",
                "edge_type": "APPLIES_PLAIN_MEANING",
                "confidence": 0.9,
                "text_span": "interprets 18 U.S.C. § 922(g)(1) using plain meaning",
            },
        ]
    }
    extraction_path = tmp_path / "extract.json"
    extraction_path.write_text(json.dumps(extraction), encoding="utf-8")

    vault_root = tmp_path / "vault"
    out = tmp_path / "run.json"
    env = dict(os.environ)
    env.update({"PYTHONPATH": str(root)})
    subprocess.run(
        [
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
            "Sample v. Test",
            "--court",
            "SCOTUS",
            "--court-level",
            "supreme",
            "--jurisdiction",
            "US",
            "--date-decided",
            "2026-02-19",
            "--primary-citation",
            "999 U.S. 999",
            "--output",
            str(out),
        ],
        check=True,
        cwd=str(root),
        env=env,
    )

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["interpretive_edge_count"] == 2
    assert payload["unresolved_count"] == 0
    assert {item["authority_type"] for item in payload["interpretive_edges"]} == {"CONSTITUTION", "STATUTE"}
    assert all(item.get("target_source_id") for item in payload["interpretive_edges"])

    case_notes = list((vault_root / "cases").rglob("*.md"))
    assert case_notes
    case_text = case_notes[0].read_text(encoding="utf-8")
    assert "interpretive_edges:" in case_text

    assert (vault_root / "sources" / "constitution" / "constitution.us.amendment.4.md").exists()
    assert (vault_root / "sources" / "statutes" / "statute.usc.18.md").exists()
