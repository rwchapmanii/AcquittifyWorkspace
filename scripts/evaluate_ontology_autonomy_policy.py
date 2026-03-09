#!/usr/bin/env python3
"""Evaluate ontology nightly validation metrics against autonomy policy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acquittify.ontology.neo4j import (
    evaluate_autonomy_policy,
    load_autonomy_policy,
    metrics_from_validation_report,
)

DEFAULT_POLICY_PATH = (
    ROOT
    / "acquittify"
    / "ontology"
    / "neo4j"
    / "policies"
    / "acquittify_autonomy_policy_v1_2026-03-08.yaml"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate ontology autonomy policy")
    parser.add_argument(
        "--policy",
        type=Path,
        default=DEFAULT_POLICY_PATH,
        help="Autonomy policy YAML path",
    )
    parser.add_argument(
        "--validation-report",
        type=Path,
        default=Path("reports/nightly_neo4j_extraction_validation.json"),
        help="Nightly validation JSON report",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("reports/nightly_ontology_autonomy_decision.json"),
        help="Autonomy decision JSON output",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=Path("reports/nightly_ontology_autonomy_decision.md"),
        help="Autonomy decision markdown output",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    policy = load_autonomy_policy(args.policy)
    report_payload = json.loads(args.validation_report.read_text(encoding="utf-8"))
    metrics = metrics_from_validation_report(report_payload)
    decision = evaluate_autonomy_policy(policy, metrics)

    out = {
        "policy_id": policy.policy_id,
        "decision": decision.decision,
        "hard_vetoes_triggered": decision.hard_vetoes_triggered,
        "failed_checks": decision.failed_checks,
        "summary": decision.summary,
        "inputs": {
            "policy": str(args.policy.resolve()),
            "validation_report": str(args.validation_report.resolve()),
        },
        "metrics_used": metrics.model_dump(mode="json", exclude_none=False),
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    md_lines = [
        "# Ontology Autonomy Decision",
        "",
        f"- Policy: `{policy.policy_id}`",
        f"- Decision: `{decision.decision}`",
        f"- Summary: {decision.summary}",
        "",
        "## Failed Checks",
        "",
    ]
    if decision.failed_checks:
        for check in decision.failed_checks:
            md_lines.append(f"- {check}")
    else:
        md_lines.append("- none")

    md_lines.extend(["", "## Hard Vetoes", ""])
    if decision.hard_vetoes_triggered:
        for veto in decision.hard_vetoes_triggered:
            md_lines.append(f"- {veto}")
    else:
        md_lines.append("- none")

    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
