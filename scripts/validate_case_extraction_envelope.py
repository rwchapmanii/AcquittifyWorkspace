#!/usr/bin/env python3
"""Validate a case extraction envelope and project it to graph payload counts.

Usage:
  python scripts/validate_case_extraction_envelope.py --input extraction.yaml
"""

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
    parser = argparse.ArgumentParser(description="Validate Neo4j case extraction envelope")
    parser.add_argument("--input", required=True, type=Path, help="YAML/JSON envelope file")
    parser.add_argument("--output", type=Path, default=None, help="Optional output JSON summary path")
    parser.add_argument(
        "--no-stub-cases",
        action="store_true",
        help="Do not emit stub case nodes for cited/appealed cases",
    )
    return parser.parse_args()


def load_payload(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".json"}:
        loaded = json.loads(raw)
    else:
        loaded = yaml.safe_load(raw)
    if not isinstance(loaded, dict):
        raise ValueError("Extraction payload must be a JSON/YAML object")
    return loaded


def summarize(envelope: CaseExtractionEnvelope, *, include_stub_cases: bool) -> dict[str, Any]:
    graph = envelope.to_graph_document(include_stub_cases=include_stub_cases)
    node_labels: dict[str, int] = {}
    rel_types: dict[str, int] = {}
    for node in graph.nodes:
        node_labels[node.label] = node_labels.get(node.label, 0) + 1
    for rel in graph.relationships:
        rel_types[rel.rel_type] = rel_types.get(rel.rel_type, 0) + 1
    return {
        "schema_name": envelope.schema_name,
        "schema_version": envelope.schema_version,
        "case_id": envelope.case.case_id,
        "node_count": len(graph.nodes),
        "relationship_count": len(graph.relationships),
        "node_labels": dict(sorted(node_labels.items())),
        "relationship_types": dict(sorted(rel_types.items())),
    }


def main() -> int:
    args = parse_args()
    payload = load_payload(args.input)
    envelope = CaseExtractionEnvelope.model_validate(payload)
    summary = summarize(envelope, include_stub_cases=not args.no_stub_cases)

    output = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
