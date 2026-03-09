#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any

import yaml

from acquittify.paths import PRECEDENT_VAULT_ROOT, REPORTS_ROOT

DEFAULT_VAULT_ROOT = PRECEDENT_VAULT_ROOT
DEFAULT_CASE_ID_FILE = DEFAULT_VAULT_ROOT / "indices" / "pilot_100_case_ids.json"
DEFAULT_REPORT_DIR = REPORTS_ROOT


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate pilot SCOTUS ontology coverage and edge constraints.")
    parser.add_argument("--vault-root", type=Path, default=DEFAULT_VAULT_ROOT, help="Path to precedent_vault")
    parser.add_argument("--case-id-file", type=Path, default=DEFAULT_CASE_ID_FILE, help="Pilot case id JSON")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR, help="Report output dir")
    return parser.parse_args()


def _split_frontmatter(raw_text: str) -> tuple[str, str]:
    text = raw_text or ""
    if not text.startswith("---\n"):
        return "", text
    marker = "\n---\n"
    end = text.find(marker, 4)
    if end == -1:
        return "", text
    return text[4:end], text[end + len(marker) :]


def _load_frontmatter(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {}
    frontmatter_text, _ = _split_frontmatter(raw)
    if not frontmatter_text.strip():
        return {}
    try:
        payload = yaml.safe_load(frontmatter_text) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_case_ids(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("case_ids"), list):
        return [str(item).strip() for item in payload.get("case_ids") if str(item).strip()]
    if isinstance(payload, list):
        return [str(item).strip() for item in payload if str(item).strip()]
    return []


def main() -> None:
    args = parse_args()
    vault_root = args.vault_root.expanduser().resolve()
    case_id_path = args.case_id_file.expanduser().resolve()
    report_dir = args.report_dir.expanduser().resolve()
    report_dir.mkdir(parents=True, exist_ok=True)

    pilot_case_ids = _load_case_ids(case_id_path)
    pilot_set = set(pilot_case_ids)

    cases_root = vault_root / "cases" / "scotus"
    case_files = sorted(cases_root.rglob("*.md"))

    cases: list[dict[str, Any]] = []
    duplicates: dict[str, list[str]] = {}
    seen: dict[str, list[str]] = {}

    for path in case_files:
        data = _load_frontmatter(path)
        case_id = str(data.get("case_id") or "").strip()
        if not case_id or case_id not in pilot_set:
            continue
        seen.setdefault(case_id, []).append(str(path))

        citation_anchors = data.get("citation_anchors") or []
        authority_anchors = data.get("authority_anchors") or []
        case_taxonomies = data.get("case_taxonomies") or []

        resolved_citations = [
            item for item in citation_anchors
            if isinstance(item, dict) and str(item.get("resolved_case_id") or "").strip()
        ]
        resolved_within_pilot = [
            item for item in resolved_citations
            if str(item.get("resolved_case_id") or "").strip() in pilot_set
        ]

        has_const = any(
            isinstance(item, dict) and str(item.get("source_type") or "").lower() == "constitution"
            for item in authority_anchors
        )
        has_statute = any(
            isinstance(item, dict) and str(item.get("source_id") or "").startswith("statute.usc.")
            for item in authority_anchors
        )
        has_reg = any(
            isinstance(item, dict) and str(item.get("source_id") or "").startswith("reg.cfr.")
            for item in authority_anchors
        )
        has_tax = bool(case_taxonomies)

        cases.append(
            {
                "case_id": case_id,
                "path": str(path),
                "citation_anchor_count": len(citation_anchors),
                "resolved_case_citation_count": len(resolved_citations),
                "resolved_case_citation_within_pilot": len(resolved_within_pilot),
                "has_constitution": has_const,
                "has_statute_title": has_statute,
                "has_reg_title": has_reg,
                "has_taxonomy": has_tax,
            }
        )

    for case_id, paths in seen.items():
        if len(paths) > 1:
            duplicates[case_id] = paths

    total_cases = len(cases)
    case_linked = sum(1 for item in cases if item["resolved_case_citation_count"] > 0)
    case_linked_within = sum(1 for item in cases if item["resolved_case_citation_within_pilot"] > 0)
    non_case_linked = sum(
        1
        for item in cases
        if item["has_constitution"] or item["has_statute_title"] or item["has_reg_title"] or item["has_taxonomy"]
    )

    total_citation_anchors = sum(item["citation_anchor_count"] for item in cases)
    total_resolved = sum(item["resolved_case_citation_count"] for item in cases)
    unresolved_rate = 0.0
    if total_citation_anchors:
        unresolved_rate = max(0.0, 1.0 - (total_resolved / total_citation_anchors))

    report = {
        "pilot_case_count": total_cases,
        "duplicate_case_id_count": len(duplicates),
        "duplicate_case_ids": duplicates,
        "case_with_case_citation_rate": (case_linked / total_cases) if total_cases else 0.0,
        "case_with_case_citation_within_pilot_rate": (case_linked_within / total_cases) if total_cases else 0.0,
        "case_with_non_case_edge_rate": (non_case_linked / total_cases) if total_cases else 0.0,
        "unresolved_case_citation_rate": unresolved_rate,
        "total_citation_anchors": total_citation_anchors,
        "total_resolved_case_citations": total_resolved,
        "cases": cases,
    }

    json_path = report_dir / "scotus_pilot_validation_report.json"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    md_lines = [
        "# SCOTUS Pilot Validation Report",
        "",
        f"pilot_case_count: {total_cases}",
        f"duplicate_case_id_count: {len(duplicates)}",
        f"case_with_case_citation_rate: {report['case_with_case_citation_rate']:.3f}",
        f"case_with_case_citation_within_pilot_rate: {report['case_with_case_citation_within_pilot_rate']:.3f}",
        f"case_with_non_case_edge_rate: {report['case_with_non_case_edge_rate']:.3f}",
        f"unresolved_case_citation_rate: {report['unresolved_case_citation_rate']:.3f}",
        "",
        "## Duplicate Case IDs",
        json.dumps(duplicates, indent=2),
        "",
    ]
    md_path = report_dir / "scotus_pilot_validation_report.md"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(json.dumps({"report": str(json_path), "markdown": str(md_path)}, indent=2))


if __name__ == "__main__":
    main()
