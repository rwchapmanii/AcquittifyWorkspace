import json
import os
from pathlib import Path
import subprocess
import sys

from acquittify.ontology.ids import build_holding_id


def test_compile_writes_source_nodes_and_applies_source_weight(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts" / "compile_precedent_ontology.py"

    text_path = tmp_path / "opinion.txt"
    text_path.write_text(
        "The court references constitutional text and LaFave treatise authority.",
        encoding="utf-8",
    )

    extraction = {
        "holdings": [
            {
                "holding_text": "Constitutional holding.",
                "if_condition": [],
                "then_consequence": [],
                "normative_strength": "binding_core",
                "normative_source": ["constitution.us.amendment.4"],
                "fact_vector": [],
                "secondary_sources": [],
                "citations_supporting": [],
            },
            {
                "holding_text": "Secondary-only holding.",
                "if_condition": [],
                "then_consequence": [],
                "normative_strength": "persuasive",
                "normative_source": ["secondary.hornbook.lafave.crimpro.6e"],
                "fact_vector": [],
                "secondary_sources": [
                    {
                        "source_id": "secondary.hornbook.lafave.crimpro.6e",
                        "title": "LaFave, Criminal Procedure (6th ed.)",
                        "topic_tags": ["Fourth Amendment"],
                    }
                ],
                "citations_supporting": [],
            },
        ],
        "issues": [
            {
                "normalized_form": "Whether source authority affects persuasive force.",
                "taxonomy": {
                    "domain": "Fourth Amendment",
                    "doctrine": "Automobile Exception",
                    "rule_type": "Authority Weight",
                },
                "required_fact_dimensions": [],
                "supporting_citations": [],
            }
        ],
        "relations": [],
    }
    extraction_path = tmp_path / "extract.json"
    extraction_path.write_text(json.dumps(extraction), encoding="utf-8")

    vault_root = tmp_path / "vault"
    out = tmp_path / "run.json"
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
        "Source Weighting Case",
        "--court",
        "SCOTUS",
        "--court-level",
        "supreme",
        "--jurisdiction",
        "US",
        "--date-decided",
        "2000-01-01",
        "--primary-citation",
        "500 U.S. 100",
        "--output",
        str(out),
    ]
    env = dict(os.environ)
    env.update({"PYTHONPATH": str(root)})
    subprocess.run(cmd, check=True, cwd=str(root), env=env)

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["source_count"] == 2

    h1 = build_holding_id(payload["case_id"], 1)
    h2 = build_holding_id(payload["case_id"], 2)
    pf = payload["metrics_summary"]["PF_holding"]
    assert pf[h1] > pf[h2]

    assert (vault_root / "sources" / "constitution" / "constitution.us.amendment.4.md").exists()
    assert (vault_root / "sources" / "secondary" / "secondary.hornbook.lafave.crimpro.6e.md").exists()
