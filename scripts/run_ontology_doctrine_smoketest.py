#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from acquittify.ontology.ids import build_holding_id


_CASE_ID_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+\.\d{4}\.[a-z0-9_]+\.[a-z0-9_]+$")


def _collect_citations(extraction: dict, primary_citation: str) -> list[str]:
    values = {primary_citation}
    for holding in extraction.get("holdings", []):
        for citation in holding.get("citations_supporting", []) or []:
            if citation:
                values.add(str(citation))
    for issue in extraction.get("issues", []):
        for citation in issue.get("supporting_citations", []) or []:
            if citation:
                values.add(str(citation))
    return sorted(values)


def _run_compile_case(
    *,
    root: Path,
    compile_script: Path,
    work_dir: Path,
    vault_root: Path,
    case_name: str,
    text: str,
    extraction: dict,
    title: str,
    court: str,
    court_level: str,
    date_decided: str,
    primary_citation: str,
) -> dict:
    text_path = work_dir / f"{case_name}.txt"
    extraction_path = work_dir / f"{case_name}.json"
    output_path = work_dir / f"{case_name}.out.json"
    text_path.write_text(text, encoding="utf-8")
    extraction_path.write_text(json.dumps(extraction), encoding="utf-8")

    cmd = [
        sys.executable,
        str(compile_script),
        "--text-file",
        str(text_path),
        "--extraction-json",
        str(extraction_path),
        "--skip-resolver",
        "--vault-root",
        str(vault_root),
        "--title",
        title,
        "--court",
        court,
        "--court-level",
        court_level,
        "--jurisdiction",
        "US",
        "--date-decided",
        date_decided,
        "--primary-citation",
        primary_citation,
        "--output",
        str(output_path),
    ]

    for citation in _collect_citations(extraction, primary_citation):
        cmd.extend(["--citation", citation])

    env = dict(**{"PYTHONPATH": str(root)})
    subprocess.run(cmd, cwd=str(root), check=True, env=env)
    return json.loads(output_path.read_text(encoding="utf-8"))


def _load_issue_index(vault_root: Path) -> list[dict]:
    path = vault_root / "indices" / "issue_index.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, list) else []


def _extract_frontmatter(text: str) -> list[str]:
    lines = text.splitlines()
    if len(lines) < 3 or lines[0].strip() != "---":
        return []
    out: list[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        out.append(line)
    return out


def _parse_yaml_list(frontmatter_lines: list[str], key: str) -> list[str]:
    values: list[str] = []
    inside = False
    key_prefix = f"{key}:"
    for line in frontmatter_lines:
        if line.startswith(key_prefix):
            inside = True
            continue
        if not inside:
            continue
        if line.startswith("  - "):
            raw = line[4:].strip()
            if raw.startswith('"') and raw.endswith('"'):
                raw = raw[1:-1]
            if raw.startswith("'") and raw.endswith("'"):
                raw = raw[1:-1]
            values.append(raw)
            continue
        if line and not line.startswith("  "):
            break
    return values


def _load_holding_citations(vault_root: Path) -> list[str]:
    out: list[str] = []
    for path in sorted((vault_root / "holdings").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        fm = _extract_frontmatter(text)
        out.extend(_parse_yaml_list(fm, "citations_supporting"))
    return out


def _load_relation_records(vault_root: Path) -> list[dict]:
    def _normalize(value: str) -> str:
        raw = (value or "").strip()
        if "." in raw:
            return raw.split(".")[-1]
        return raw

    records: list[dict] = []
    for path in sorted((vault_root / "relations").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        fm = _extract_frontmatter(text)
        values: dict[str, str] = {}
        for line in fm:
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            values[key] = value
        if {"source_holding_id", "target_holding_id", "relation_type"}.issubset(values):
            records.append(
                {
                    "source_holding_id": values["source_holding_id"],
                    "target_holding_id": values["target_holding_id"],
                    "relation_type": _normalize(values["relation_type"]),
                }
            )
    return records


def _vault_snapshot(vault_root: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for path in sorted(vault_root.rglob("*")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(vault_root))
        snapshot[rel] = path.read_text(encoding="utf-8")
    return snapshot


def _build_impound_case_text() -> tuple[str, dict[str, int]]:
    seg_apply = "The CA9 panel applies Carroll, 267 U.S. 132, in routine vehicle stops."
    gap1 = " " + ("x" * 280) + " "
    seg_limit = "Ross, 456 U.S. 798, limits container searches when facts materially differ."
    gap2 = " " + ("y" * 280) + " "
    seg_overrule = "This panel overruled an earlier expansive reading in impound context."
    text = seg_apply + gap1 + seg_limit + gap2 + seg_overrule
    spans = {
        "apply_start": text.index("applies"),
        "apply_end": text.index("routine vehicle") + len("routine vehicle"),
        "limit_start": text.index("limits"),
        "limit_end": text.index("materially differ.") + len("materially differ."),
        "overrule_start": text.index("overruled"),
        "overrule_end": text.index("impound context.") + len("impound context."),
    }
    return text, spans


def _execute_sequence(root: Path, compile_script: Path, vault_root: Path, work_dir: Path) -> tuple[dict[str, dict], dict[str, list[dict]], dict[str, str]]:
    payloads: dict[str, dict] = {}
    snapshots: dict[str, list[dict]] = {}
    holding_ids: dict[str, str] = {}

    carroll_payload = _run_compile_case(
        root=root,
        compile_script=compile_script,
        work_dir=work_dir,
        vault_root=vault_root,
        case_name="carroll",
        text="Under Carroll, 267 U.S. 132, the automobile exception applies with probable cause.",
        extraction={
            "holdings": [
                {
                    "holding_text": "If probable cause exists for a vehicle, warrantless search is permitted.",
                    "if_condition": [{"predicate": "probable_cause", "value": True}],
                    "then_consequence": [{"predicate": "warrantless_search_permitted", "value": True}],
                    "normative_strength": "binding_core",
                    "normative_source": ["constitution.us.amendment.4"],
                    "fact_vector": [{"dimension": "vehicle_mobility", "value": "inherent"}],
                    "secondary_sources": [],
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
                    "required_fact_dimensions": ["vehicle_status", "probable_cause_status"],
                    "supporting_citations": ["267 U.S. 132"],
                }
            ],
            "relations": [],
        },
        title="Carroll v. United States",
        court="SCOTUS",
        court_level="supreme",
        date_decided="1925-03-02",
        primary_citation="267 U.S. 132",
    )
    payloads["carroll"] = carroll_payload
    snapshots["carroll"] = _load_issue_index(vault_root)
    holding_ids["carroll"] = build_holding_id(carroll_payload["case_id"], 1)

    ross_payload = _run_compile_case(
        root=root,
        compile_script=compile_script,
        work_dir=work_dir,
        vault_root=vault_root,
        case_name="ross",
        text="Ross, 456 U.S. 798, extends Carroll, 267 U.S. 132, to containers in a vehicle.",
        extraction={
            "holdings": [
                {
                    "holding_text": "The automobile exception extends to containers in the vehicle.",
                    "if_condition": [{"predicate": "object_type", "value": "container_in_vehicle"}],
                    "then_consequence": [{"predicate": "search_scope", "value": "container_allowed"}],
                    "normative_strength": "binding_core",
                    "normative_source": ["constitution.us.amendment.4"],
                    "fact_vector": [{"dimension": "container_scope", "value": "included"}],
                    "secondary_sources": [],
                    "citations_supporting": ["456 U.S. 798", "267 U.S. 132"],
                }
            ],
            "issues": [
                {
                    "normalized_form": "Whether the automobile exception includes container searches.",
                    "taxonomy": {
                        "domain": "Fourth Amendment",
                        "doctrine": "Automobile Exception",
                        "rule_type": "Container Scope",
                    },
                    "required_fact_dimensions": ["container_scope"],
                    "supporting_citations": ["456 U.S. 798", "267 U.S. 132"],
                }
            ],
            "relations": [
                {
                    "source_holding_index": 0,
                    "target_holding_index": None,
                    "relation_type": "extends",
                    "citation_type": "controlling",
                    "confidence": 0.84,
                    "evidence_span": {"start_char": 20, "end_char": 66},
                }
            ],
        },
        title="United States v. Ross",
        court="SCOTUS",
        court_level="supreme",
        date_decided="1982-06-01",
        primary_citation="456 U.S. 798",
    )
    payloads["ross"] = ross_payload
    snapshots["ross"] = _load_issue_index(vault_root)
    holding_ids["ross"] = build_holding_id(ross_payload["case_id"], 1)

    acevedo_payload = _run_compile_case(
        root=root,
        compile_script=compile_script,
        work_dir=work_dir,
        vault_root=vault_root,
        case_name="acevedo",
        text="Acevedo, 500 U.S. 565, clarified Ross, 456 U.S. 798, and harmonized Carroll, 267 U.S. 132.",
        extraction={
            "holdings": [
                {
                    "holding_text": "Container clarification harmonizes prior automobile exception cases.",
                    "if_condition": [{"predicate": "container_type", "value": "mobile_vehicle_container"}],
                    "then_consequence": [{"predicate": "search_scope", "value": "clarified"}],
                    "normative_strength": "binding_core",
                    "normative_source": ["constitution.us.amendment.4"],
                    "fact_vector": [{"dimension": "container_scope", "value": "clarified"}],
                    "secondary_sources": [],
                    "citations_supporting": ["500 U.S. 565", "456 U.S. 798", "267 U.S. 132"],
                }
            ],
            "issues": [
                {
                    "normalized_form": "Whether prior container-scope automobile precedent is clarified.",
                    "taxonomy": {
                        "domain": "Fourth Amendment",
                        "doctrine": "Automobile Exception",
                        "rule_type": "Container Scope",
                    },
                    "required_fact_dimensions": ["container_scope"],
                    "supporting_citations": ["500 U.S. 565", "456 U.S. 798", "267 U.S. 132"],
                }
            ],
            "relations": [
                {
                    "source_holding_index": 0,
                    "target_holding_id": holding_ids["ross"],
                    "relation_type": "clarifies",
                    "citation_type": "controlling",
                    "confidence": 0.83,
                    "evidence_span": {"start_char": 20, "end_char": 72},
                }
            ],
        },
        title="California v. Acevedo",
        court="SCOTUS",
        court_level="supreme",
        date_decided="1991-05-30",
        primary_citation="500 U.S. 565",
    )
    payloads["acevedo"] = acevedo_payload
    snapshots["acevedo"] = _load_issue_index(vault_root)
    holding_ids["acevedo"] = build_holding_id(acevedo_payload["case_id"], 1)

    ca9_payload = _run_compile_case(
        root=root,
        compile_script=compile_script,
        work_dir=work_dir,
        vault_root=vault_root,
        case_name="ca9_apply",
        text="The Ninth Circuit in 600 F.3d 100 applies Carroll, 267 U.S. 132, in routine stops.",
        extraction={
            "holdings": [
                {
                    "holding_text": "Circuit panel applies automobile exception to routine mobile stops.",
                    "if_condition": [{"predicate": "vehicle_status", "value": "mobile"}],
                    "then_consequence": [{"predicate": "warrantless_search_permitted", "value": True}],
                    "normative_strength": "binding_narrow",
                    "normative_source": ["constitution.us.amendment.4"],
                    "fact_vector": [{"dimension": "vehicle_status", "value": "mobile"}],
                    "secondary_sources": [],
                    "citations_supporting": ["600 F.3d 100", "267 U.S. 132"],
                }
            ],
            "issues": [
                {
                    "normalized_form": "Whether the automobile exception applies in routine circuit cases.",
                    "taxonomy": {
                        "domain": "Fourth Amendment",
                        "doctrine": "Automobile Exception",
                        "rule_type": "Exception Applicability",
                    },
                    "required_fact_dimensions": ["vehicle_status"],
                    "supporting_citations": ["600 F.3d 100", "267 U.S. 132"],
                }
            ],
            "relations": [
                {
                    "source_holding_index": 0,
                    "target_holding_id": holding_ids["carroll"],
                    "relation_type": "applies",
                    "citation_type": "controlling",
                    "confidence": 0.8,
                    "evidence_span": {"start_char": 45, "end_char": 82},
                }
            ],
        },
        title="United States v. Example Ninth",
        court="CA9",
        court_level="circuit",
        date_decided="2010-01-01",
        primary_citation="600 F.3d 100",
    )
    payloads["ca9_apply"] = ca9_payload
    snapshots["ca9_apply"] = _load_issue_index(vault_root)
    holding_ids["ca9_apply"] = build_holding_id(ca9_payload["case_id"], 1)

    impound_text, spans = _build_impound_case_text()
    ca2_impound_payload = _run_compile_case(
        root=root,
        compile_script=compile_script,
        work_dir=work_dir,
        vault_root=vault_root,
        case_name="ca2_impound",
        text=impound_text,
        extraction={
            "holdings": [
                {
                    "holding_text": "Impounded vehicle context narrows exception application.",
                    "if_condition": [{"predicate": "custody_status", "value": "impounded"}],
                    "then_consequence": [{"predicate": "warrantless_search_permitted", "value": False}],
                    "normative_strength": "binding_narrow",
                    "normative_source": ["constitution.us.amendment.4"],
                    "fact_vector": [{"dimension": "custody_status", "value": "impounded"}],
                    "secondary_sources": [],
                    "citations_supporting": ["610 F.3d 200", "267 U.S. 132", "456 U.S. 798"],
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
                    "required_fact_dimensions": ["custody_status"],
                    "supporting_citations": ["610 F.3d 200", "267 U.S. 132", "456 U.S. 798"],
                }
            ],
            "relations": [
                {
                    "source_holding_id": holding_ids["ca9_apply"],
                    "target_holding_index": 0,
                    "relation_type": "applies",
                    "citation_type": "controlling",
                    "confidence": 0.9,
                    "evidence_span": {"start_char": spans["apply_start"], "end_char": spans["apply_end"]},
                },
                {
                    "source_holding_id": holding_ids["ross"],
                    "target_holding_index": 0,
                    "relation_type": "limits",
                    "citation_type": "controlling",
                    "confidence": 0.9,
                    "evidence_span": {"start_char": spans["limit_start"], "end_char": spans["limit_end"]},
                },
                {
                    "source_holding_index": 0,
                    "target_holding_index": 0,
                    "relation_type": "clarifies",
                    "citation_type": "controlling",
                    "confidence": 0.72,
                    "evidence_span": {"start_char": spans["overrule_start"], "end_char": spans["overrule_end"]},
                },
            ],
        },
        title="United States v. Example Second",
        court="CA2",
        court_level="circuit",
        date_decided="2012-02-02",
        primary_citation="610 F.3d 200",
    )
    payloads["ca2_impound"] = ca2_impound_payload
    snapshots["ca2_impound"] = _load_issue_index(vault_root)
    holding_ids["ca2_impound"] = build_holding_id(ca2_impound_payload["case_id"], 1)

    return payloads, snapshots, holding_ids


def run_smoketest(*, root: Path, vault_root: Path, work_dir: Path) -> dict:
    compile_script = root / "scripts" / "compile_precedent_ontology.py"

    payloads_first, snapshots_first, holding_ids = _execute_sequence(root, compile_script, vault_root, work_dir)
    first_snapshot = _vault_snapshot(vault_root)
    payloads_second, snapshots_second, _ = _execute_sequence(root, compile_script, vault_root, work_dir)
    second_snapshot = _vault_snapshot(vault_root)

    issue_index = snapshots_first["ca2_impound"]
    issue_by_id = {item.get("issue_id"): item for item in issue_index}
    variant_issue_id = payloads_first["ca2_impound"]["canonicalization_decisions"][0]["issue_id"]
    variant_issue = issue_by_id.get(variant_issue_id, {})
    variant_metrics = variant_issue.get("metrics", {}) if isinstance(variant_issue, dict) else {}

    relation_records = _load_relation_records(vault_root)
    holding_citations = _load_holding_citations(vault_root)
    issue_citations = []
    for issue in issue_index:
        anchors = issue.get("anchors", {}) if isinstance(issue, dict) else {}
        issue_citations.extend(anchors.get("canonical_citations", []) or [])
    all_anchor_values = [str(value) for value in holding_citations + issue_citations if str(value).strip()]
    resolved_anchor_values = [value for value in all_anchor_values if _CASE_ID_RE.match(value)]
    anchor_ratio = 1.0 if not all_anchor_values else (len(resolved_anchor_values) / len(all_anchor_values))

    doctrines = {
        (issue.get("taxonomy", {}) or {}).get("doctrine", "")
        for issue in issue_index
        if isinstance(issue, dict)
    }

    carroll_h1 = holding_ids["carroll"]
    ross_h1 = holding_ids["ross"]
    acevedo_h1 = holding_ids["acevedo"]
    impound_h1 = holding_ids["ca2_impound"]

    ross_to_carroll = any(
        r["source_holding_id"] == ross_h1
        and r["target_holding_id"] == carroll_h1
        and r["relation_type"] in {"extends", "clarifies"}
        for r in relation_records
    )
    acevedo_clarifies = any(
        r["source_holding_id"] == acevedo_h1
        and r["target_holding_id"] in {ross_h1, carroll_h1}
        and r["relation_type"] == "clarifies"
        for r in relation_records
    )
    has_overrules = any(r["relation_type"] == "overrules" for r in relation_records)

    carroll_pf = payloads_first["carroll"]["metrics_summary"]["PF_holding"][carroll_h1]
    impound_pf = payloads_first["ca2_impound"]["metrics_summary"]["PF_holding"][impound_h1]
    variant_consensus = variant_metrics.get("consensus")
    variant_drift = variant_metrics.get("drift")

    checks = {
        "citation_anchoring_ratio_ge_0_9": anchor_ratio >= 0.9,
        "all_issues_have_canonical_citations": all(
            ((issue.get("anchors", {}) or {}).get("canonical_citations", []) for issue in issue_index)
        ),
        "taxonomy_small_and_single_doctrine": len(issue_index) <= 3 and doctrines == {"Automobile Exception"},
        "ross_to_carroll_relation_plausible": ross_to_carroll,
        "acevedo_clarifies_prior_branch": acevedo_clarifies,
        "explicit_overrule_detected": has_overrules,
        "carroll_pf_above_impound_pf": carroll_pf > impound_pf,
        "impound_issue_shows_split_signal": (
            isinstance(variant_consensus, (int, float))
            and isinstance(variant_drift, (int, float))
            and variant_consensus < 1.0
            and variant_drift > 0.0
        ),
        "idempotent_final_vault_snapshot": first_snapshot == second_snapshot,
    }

    details = {
        "anchor_ratio": round(anchor_ratio, 6),
        "issue_count": len(issue_index),
        "doctrines": sorted(doctrines),
        "carroll_pf": carroll_pf,
        "impound_pf": impound_pf,
        "variant_issue_id": variant_issue_id,
        "variant_consensus": variant_consensus,
        "variant_drift": variant_drift,
        "relation_count": len(relation_records),
        "second_pass_changed_counts": {
            key: payload["write_result"]["changed_count"] for key, payload in payloads_second.items()
        },
        "second_pass_issue_counts": {
            key: payload["issue_count"] for key, payload in payloads_second.items()
        },
    }

    return {
        "passed": all(checks.values()),
        "checks": checks,
        "details": details,
        "case_ids": {key: payloads_first[key]["case_id"] for key in sorted(payloads_first.keys())},
        "holding_ids": holding_ids,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run doctrine smoke harness for ontology compiler.")
    parser.add_argument("--vault-root", type=Path, default=None, help="Output vault root for smoke harness")
    parser.add_argument("--work-dir", type=Path, default=None, help="Working directory for temporary input/output files")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON report output path")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    root = PROJECT_ROOT

    if args.vault_root is None:
        with tempfile.TemporaryDirectory(prefix="ontology_smoke_vault_") as temp_vault:
            vault_root = Path(temp_vault)
            if args.work_dir is None:
                with tempfile.TemporaryDirectory(prefix="ontology_smoke_work_") as temp_work:
                    report = run_smoketest(root=root, vault_root=vault_root, work_dir=Path(temp_work))
            else:
                args.work_dir.mkdir(parents=True, exist_ok=True)
                report = run_smoketest(root=root, vault_root=vault_root, work_dir=args.work_dir)
    else:
        args.vault_root.mkdir(parents=True, exist_ok=True)
        if args.work_dir is None:
            with tempfile.TemporaryDirectory(prefix="ontology_smoke_work_") as temp_work:
                report = run_smoketest(root=root, vault_root=args.vault_root, work_dir=Path(temp_work))
        else:
            args.work_dir.mkdir(parents=True, exist_ok=True)
            report = run_smoketest(root=root, vault_root=args.vault_root, work_dir=args.work_dir)

    output_text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output_text + "\n", encoding="utf-8")
    print(output_text)
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
