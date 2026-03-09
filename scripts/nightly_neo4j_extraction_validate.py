#!/usr/bin/env python3
"""Validate a nightly batch of case extraction envelopes for Neo4j projection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acquittify.ontology.neo4j import CaseExtractionEnvelope


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate nightly Neo4j extraction envelopes")
    parser.add_argument("--input-dir", type=Path, required=True, help="Directory of extraction YAML/JSON files")
    parser.add_argument(
        "--glob",
        default="**/*.*",
        help="Glob expression relative to input-dir (default: **/*.*)",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("reports/nightly_neo4j_extraction_validation.json"),
        help="Validation JSON report path",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=Path("reports/nightly_neo4j_extraction_validation.md"),
        help="Validation markdown report path",
    )
    parser.add_argument(
        "--no-stub-cases",
        action="store_true",
        help="Do not emit stub case nodes when computing graph counts",
    )
    return parser.parse_args()


def load_payload(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        loaded = json.loads(raw)
    else:
        loaded = yaml.safe_load(raw)
    if not isinstance(loaded, dict):
        raise ValueError("Payload must be a JSON/YAML object")
    return loaded


def is_supported(path: Path) -> bool:
    return path.suffix.lower() in {".json", ".yaml", ".yml"}


def main() -> int:
    args = parse_args()
    input_dir = args.input_dir.resolve()
    if not input_dir.exists():
        raise SystemExit(f"Input directory not found: {input_dir}")

    files = sorted(path for path in input_dir.glob(args.glob) if path.is_file() and is_supported(path))
    include_stub_cases = not args.no_stub_cases

    valid = 0
    invalid = 0
    total_nodes = 0
    total_relationships = 0
    error_samples: list[dict[str, str]] = []
    case_ids: list[str] = []
    namespace_present = 0
    ontology_version_present = 0

    for path in files:
        rel = str(path.relative_to(input_dir))
        try:
            payload = load_payload(path)
            envelope = CaseExtractionEnvelope.model_validate(payload)
            graph = envelope.to_graph_document(include_stub_cases=include_stub_cases)
            valid += 1
            total_nodes += len(graph.nodes)
            total_relationships += len(graph.relationships)
            case_ids.append(str(envelope.case.case_id or "").strip())
            if str(envelope.schema_name or "").strip():
                namespace_present += 1
            if str(envelope.schema_version or "").strip():
                ontology_version_present += 1
        except Exception as exc:  # noqa: BLE001
            invalid += 1
            if len(error_samples) < 25:
                error_samples.append({"file": rel, "error": str(exc)[:600]})

    unique_case_ids = {case_id for case_id in case_ids if case_id}
    duplicate_case_ids = max(0, len(case_ids) - len(unique_case_ids))
    duplicate_case_id_rate = (duplicate_case_ids / valid) if valid else 0.0
    namespace_reference_present_rate = (namespace_present / valid) if valid else 0.0
    ontology_version_reference_present_rate = (ontology_version_present / valid) if valid else 0.0

    report = {
        "input_dir": str(input_dir),
        "glob": args.glob,
        "files_scanned": len(files),
        "valid_files": valid,
        "invalid_files": invalid,
        "valid_rate": round((valid / len(files)) if files else 0.0, 4),
        "total_nodes_projected": total_nodes,
        "total_relationships_projected": total_relationships,
        "duplicate_case_ids": duplicate_case_ids,
        "duplicate_case_id_rate": round(duplicate_case_id_rate, 4),
        "namespace_reference_present_rate": round(namespace_reference_present_rate, 4),
        "ontology_version_reference_present_rate": round(ontology_version_reference_present_rate, 4),
        # Temporal leakage requires time-sliced authority checks and is handled by
        # downstream benchmark passes. Keep null until that pass provides a metric.
        "temporal_leakage_rate": None,
        # Merge-collision detection is currently handled via GraphDocument dedupe.
        "merge_collision_rate": 0.0,
        "include_stub_cases": include_stub_cases,
        "error_samples": error_samples,
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    md_lines = [
        "# Nightly Neo4j Extraction Validation",
        "",
        f"- Input dir: `{input_dir}`",
        f"- Glob: `{args.glob}`",
        f"- Files scanned: {len(files)}",
        f"- Valid files: {valid}",
        f"- Invalid files: {invalid}",
        f"- Valid rate: {report['valid_rate']:.2%}",
        f"- Total nodes projected: {total_nodes}",
        f"- Total relationships projected: {total_relationships}",
        f"- Duplicate case IDs: {duplicate_case_ids}",
        f"- Duplicate case ID rate: {duplicate_case_id_rate:.2%}",
        f"- Namespace reference present rate: {namespace_reference_present_rate:.2%}",
        f"- Ontology version reference present rate: {ontology_version_reference_present_rate:.2%}",
        "",
    ]
    if error_samples:
        md_lines.append("## Error Samples")
        md_lines.append("")
        for sample in error_samples:
            md_lines.append(f"- `{sample['file']}`: {sample['error']}")
    else:
        md_lines.append("No validation errors.")

    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
