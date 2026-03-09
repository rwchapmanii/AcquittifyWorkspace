#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from acquittify.ontology.metrics import apply_metrics, load_params
from acquittify.ontology.schemas import HoldingNode, IssueNode, RelationNode
from acquittify.ontology.yaml_utils import dump_yaml, markdown_with_frontmatter
from acquittify.paths import PRECEDENT_VAULT_ROOT


DEFAULT_VAULT_ROOT = PRECEDENT_VAULT_ROOT


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild ontology metrics.yaml and issue_index.json from vault artifacts.")
    parser.add_argument("--vault-root", type=Path, default=DEFAULT_VAULT_ROOT, help="Path to precedent_vault")
    parser.add_argument("--dry-run", action="store_true", help="Compute and print summary without writing files")
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


def _load_frontmatter_dict(path: Path) -> tuple[dict[str, Any], str]:
    raw_text = path.read_text(encoding="utf-8", errors="ignore")
    frontmatter_text, body = _split_frontmatter(raw_text)
    if not frontmatter_text.strip():
        return {}, body
    payload = yaml.safe_load(frontmatter_text) or {}
    return (payload if isinstance(payload, dict) else {}), body


def _model_dump(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()  # type: ignore[attr-defined]
    if hasattr(model, "dict"):
        return model.dict()  # type: ignore[attr-defined]
    return dict(model)


def _normalize_enum_suffix(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if "." in text:
        return text.split(".")[-1]
    return text


def _normalize_holding_payload(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    out["normative_strength"] = _normalize_enum_suffix(out.get("normative_strength"))
    return out


def _normalize_relation_payload(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    out["relation_type"] = _normalize_enum_suffix(out.get("relation_type"))
    out["citation_type"] = _normalize_enum_suffix(out.get("citation_type"))
    return out


def _write_if_changed(path: Path, content: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_text(encoding="utf-8", errors="ignore")
        if existing == content:
            return False
    path.write_text(content, encoding="utf-8")
    return True


def main() -> None:
    args = parse_args()
    vault_root = args.vault_root.expanduser().resolve()

    holdings_dir = vault_root / "holdings"
    issues_dir = vault_root / "issues" / "taxonomy"
    relations_dir = vault_root / "relations"
    indices_dir = vault_root / "indices"

    holding_paths = sorted(holdings_dir.glob("*.md"))
    issue_paths = sorted(issues_dir.glob("*.md"))
    relation_paths = sorted(relations_dir.glob("*.md"))

    holdings: list[HoldingNode] = []
    holding_body_map: dict[str, str] = {}
    holding_path_map: dict[str, Path] = {}
    for path in holding_paths:
        payload, body = _load_frontmatter_dict(path)
        try:
            node = HoldingNode(**_normalize_holding_payload(payload))
        except Exception:
            continue
        holdings.append(node)
        holding_body_map[node.holding_id] = body
        holding_path_map[node.holding_id] = path

    issues: list[IssueNode] = []
    issue_body_map: dict[str, str] = {}
    issue_path_map: dict[str, Path] = {}
    for path in issue_paths:
        payload, body = _load_frontmatter_dict(path)
        try:
            node = IssueNode(**payload)
        except Exception:
            continue
        issues.append(node)
        issue_body_map[node.issue_id] = body
        issue_path_map[node.issue_id] = path

    relations: list[RelationNode] = []
    for path in relation_paths:
        payload, _ = _load_frontmatter_dict(path)
        try:
            relations.append(RelationNode(**_normalize_relation_payload(payload)))
        except Exception:
            continue

    params_path = indices_dir / "params.yaml"
    params = load_params(params_path if params_path.exists() else None)
    bundle = apply_metrics(holdings=holdings, issues=issues, relations=relations, params=params)

    metrics_payload = {**bundle.summary, "explainability": bundle.explainability}
    issue_index_payload = [_model_dump(item) for item in sorted(issues, key=lambda obj: obj.issue_id)]

    changed = 0
    if not args.dry_run:
        for node in holdings:
            path = holding_path_map.get(node.holding_id)
            if not path:
                continue
            body = holding_body_map.get(node.holding_id, "")
            content = markdown_with_frontmatter(_model_dump(node), body if body.endswith("\n") else f"{body}\n")
            changed += 1 if _write_if_changed(path, content) else 0

        for node in issues:
            path = issue_path_map.get(node.issue_id)
            if not path:
                continue
            body = issue_body_map.get(node.issue_id, "")
            content = markdown_with_frontmatter(_model_dump(node), body if body.endswith("\n") else f"{body}\n")
            changed += 1 if _write_if_changed(path, content) else 0

        metrics_path = indices_dir / "metrics.yaml"
        metrics_content = dump_yaml(metrics_payload) + "\n"
        changed += 1 if _write_if_changed(metrics_path, metrics_content) else 0

        issue_index_path = indices_dir / "issue_index.json"
        issue_index_content = json.dumps(issue_index_payload, indent=2, ensure_ascii=False) + "\n"
        changed += 1 if _write_if_changed(issue_index_path, issue_index_content) else 0

    summary = {
        "vault_root": str(vault_root),
        "holdings_loaded": len(holdings),
        "issues_loaded": len(issues),
        "relations_loaded": len(relations),
        "holding_count_metrics": bundle.summary.get("holding_count", 0),
        "issue_count_metrics": bundle.summary.get("issue_count", 0),
        "changed_files": changed,
        "dry_run": bool(args.dry_run),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
