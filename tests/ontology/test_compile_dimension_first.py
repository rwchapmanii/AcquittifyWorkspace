import json
import os
from pathlib import Path
import subprocess
import sys


def _run_compile(
    *,
    root: Path,
    script: Path,
    tmp_path: Path,
    vault_root: Path,
    fixture_name: str,
    text: str,
    extraction: dict,
    title: str,
    date_decided: str,
    primary_citation: str,
) -> dict:
    text_path = tmp_path / f"{fixture_name}.txt"
    extract_path = tmp_path / f"{fixture_name}.json"
    out_path = tmp_path / f"{fixture_name}.out.json"

    text_path.write_text(text, encoding="utf-8")
    extract_path.write_text(json.dumps(extraction), encoding="utf-8")

    cmd = [
        sys.executable,
        str(script),
        "--text-file",
        str(text_path),
        "--extraction-json",
        str(extract_path),
        "--skip-resolver",
        "--vault-root",
        str(vault_root),
        "--title",
        title,
        "--court",
        "SCOTUS",
        "--court-level",
        "supreme",
        "--jurisdiction",
        "US",
        "--date-decided",
        date_decided,
        "--primary-citation",
        primary_citation,
        "--output",
        str(out_path),
    ]

    env = dict(os.environ)
    env.update({"PYTHONPATH": str(root)})
    subprocess.run(cmd, check=True, cwd=str(root), env=env)
    return json.loads(out_path.read_text(encoding="utf-8"))


def test_compile_uses_dimension_first_issue_attachment(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts" / "compile_precedent_ontology.py"
    vault_root = tmp_path / "vault"

    first_extraction = {
        "holdings": [
            {
                "holding_text": "If probable cause exists, warrantless search is permitted.",
                "if_condition": [{"predicate": "probable_cause", "value": True}],
                "then_consequence": [{"predicate": "warrantless_search_permitted", "value": True}],
                "normative_strength": "binding_core",
                "fact_vector": [{"dimension": "vehicle_mobility", "value": "inherent"}],
                "citations_supporting": ["267 U.S. 132"],
            }
        ],
        "issues": [
            {
                "normalized_form": "Whether the automobile exception applies.",
                "taxonomy": {
                    "domain": "Fourth Amendment",
                    "doctrine": "Automobile Exception",
                    "rule_type": "Exception Applicability",
                },
                "required_fact_dimensions": ["vehicle_status"],
                "supporting_citations": ["267 U.S. 132"],
            }
        ],
        "relations": [],
    }

    first = _run_compile(
        root=root,
        script=script,
        tmp_path=tmp_path,
        vault_root=vault_root,
        fixture_name="first_dimension",
        text="Under Carroll, 267 U.S. 132, probable cause allows search.",
        extraction=first_extraction,
        title="Carroll v. United States",
        date_decided="1925-03-02",
        primary_citation="267 U.S. 132",
    )

    assert first["issue_count"] == 1

    second_extraction = {
        "holdings": [
            {
                "holding_text": "Search of impounded car remains under automobile exception.",
                "if_condition": [{"predicate": "custody_status", "value": "impounded"}],
                "then_consequence": [{"predicate": "warrantless_search_permitted", "value": True}],
                "normative_strength": "binding_narrow",
                "fact_vector": [{"dimension": "custody_status", "value": "impounded"}],
                "citations_supporting": ["267 U.S. 132"],
            }
        ],
        "issues": [
            {
                "normalized_form": "Whether the automobile exception applies when vehicle is impounded at station house.",
                "taxonomy": {
                    "domain": "Fourth Amendment",
                    "doctrine": "Automobile Exception",
                    "rule_type": "",
                },
                "required_fact_dimensions": [],
                "supporting_citations": [],
            }
        ],
        "relations": [],
    }

    second = _run_compile(
        root=root,
        script=script,
        tmp_path=tmp_path,
        vault_root=vault_root,
        fixture_name="second_dimension",
        text="The vehicle was impounded, but the exception still applied.",
        extraction=second_extraction,
        title="Later Automobile Case",
        date_decided="1999-01-01",
        primary_citation="999 U.S. 111",
    )

    assert second["issue_count"] == 1

    issue_index = json.loads((vault_root / "indices" / "issue_index.json").read_text(encoding="utf-8"))
    assert len(issue_index) == 1
    required_dims = issue_index[0]["dimensions"]["required_fact_dimensions"]
    assert "vehicle_status" in required_dims
    assert "custody_status" in required_dims

    holding_files = sorted((vault_root / "holdings").glob("*.md"))
    assert holding_files
    holding_text = "\n".join(path.read_text(encoding="utf-8") for path in holding_files)
    assert 'dimension: "vehicle_mobility"' in holding_text
    assert 'dimension: "custody_status"' in holding_text
