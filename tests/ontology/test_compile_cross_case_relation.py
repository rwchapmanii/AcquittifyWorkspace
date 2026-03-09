import json
import os
from pathlib import Path
import subprocess
import sys

from acquittify.ontology.ids import build_holding_id


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


def test_compile_supports_cross_case_relation_targeting_existing_holding(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts" / "compile_precedent_ontology.py"
    vault_root = tmp_path / "vault"

    carroll_extraction = {
        "holdings": [
            {
                "holding_text": "If probable cause exists, warrantless search of an automobile is permitted.",
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
        "relations": [],
    }

    first_payload = _run_compile(
        root=root,
        script=script,
        tmp_path=tmp_path,
        vault_root=vault_root,
        fixture_name="carroll",
        text="Under Carroll, 267 U.S. 132, we hold the search valid.",
        extraction=carroll_extraction,
        title="Carroll v. United States",
        date_decided="1925-03-02",
        primary_citation="267 U.S. 132",
    )
    target_holding_id = build_holding_id(first_payload["case_id"], 1)

    ross_extraction = {
        "holdings": [
            {
                "holding_text": "The automobile exception extends to containers in the vehicle.",
                "if_condition": [{"predicate": "object_type", "value": "container_in_vehicle"}],
                "then_consequence": [{"predicate": "search_scope", "value": "container_allowed"}],
                "normative_strength": "binding_core",
                "citations_supporting": ["456 U.S. 798"],
            }
        ],
        "issues": [
            {
                "normalized_form": "Whether the automobile exception includes containers in the vehicle.",
                "taxonomy": {
                    "domain": "Fourth Amendment",
                    "doctrine": "Automobile Exception",
                    "rule_type": "Container Scope",
                },
                "supporting_citations": ["456 U.S. 798", "267 U.S. 132"],
            }
        ],
        "relations": [
            {
                "source_holding_index": 0,
                "target_holding_id": target_holding_id,
                "relation_type": "extends",
                "citation_type": "controlling",
                "confidence": 0.83,
                "evidence_span": {"start_char": 0, "end_char": 24},
            }
        ],
    }

    second_payload = _run_compile(
        root=root,
        script=script,
        tmp_path=tmp_path,
        vault_root=vault_root,
        fixture_name="ross",
        text="Ross extends Carroll to container searches.",
        extraction=ross_extraction,
        title="United States v. Ross",
        date_decided="1982-06-01",
        primary_citation="456 U.S. 798",
    )

    assert second_payload["relation_count"] == 1
    relation_files = sorted((vault_root / "relations").glob("*.md"))
    assert relation_files
    relation_text = "\n".join(path.read_text(encoding="utf-8") for path in relation_files)
    assert f'target_holding_id: "{target_holding_id}"' in relation_text


def test_compile_infers_cross_case_relation_target_from_citation(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts" / "compile_precedent_ontology.py"
    vault_root = tmp_path / "vault"

    carroll_extraction = {
        "holdings": [
            {
                "holding_text": "If probable cause exists, warrantless search of an automobile is permitted.",
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
        "relations": [],
    }

    first_payload = _run_compile(
        root=root,
        script=script,
        tmp_path=tmp_path,
        vault_root=vault_root,
        fixture_name="carroll_infer",
        text="Under Carroll, 267 U.S. 132, we hold the search valid.",
        extraction=carroll_extraction,
        title="Carroll v. United States",
        date_decided="1925-03-02",
        primary_citation="267 U.S. 132",
    )
    target_holding_id = build_holding_id(first_payload["case_id"], 1)

    ross_extraction = {
        "holdings": [
            {
                "holding_text": "The automobile exception extends to containers in the vehicle.",
                "if_condition": [{"predicate": "object_type", "value": "container_in_vehicle"}],
                "then_consequence": [{"predicate": "search_scope", "value": "container_allowed"}],
                "normative_strength": "binding_core",
                "citations_supporting": ["456 U.S. 798"],
            }
        ],
        "issues": [
            {
                "normalized_form": "Whether the automobile exception includes containers in the vehicle.",
                "taxonomy": {
                    "domain": "Fourth Amendment",
                    "doctrine": "Automobile Exception",
                    "rule_type": "Container Scope",
                },
                "supporting_citations": ["456 U.S. 798", "267 U.S. 132"],
            }
        ],
        "relations": [
            {
                "source_holding_index": 0,
                "target_holding_index": None,
                "relation_type": "extends",
                "citation_type": "controlling",
                "confidence": 0.83,
                "evidence_span": {"start_char": 0, "end_char": 24},
            }
        ],
    }

    second_payload = _run_compile(
        root=root,
        script=script,
        tmp_path=tmp_path,
        vault_root=vault_root,
        fixture_name="ross_infer",
        text="Ross extends Carroll, 267 U.S. 132, to container searches.",
        extraction=ross_extraction,
        title="United States v. Ross",
        date_decided="1982-06-01",
        primary_citation="456 U.S. 798",
    )

    assert second_payload["relation_count"] == 1
    relation_files = sorted((vault_root / "relations").glob("*.md"))
    assert relation_files
    relation_text = "\n".join(path.read_text(encoding="utf-8") for path in relation_files)
    assert f'target_holding_id: "{target_holding_id}"' in relation_text
