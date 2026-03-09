#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

import yaml

from acquittify.metadata_extract import normalize_citation
from acquittify.ontology.vault_writer import VaultWriter
from acquittify.paths import PRECEDENT_VAULT_ROOT


DEFAULT_VAULT_ROOT = PRECEDENT_VAULT_ROOT
DEFAULT_INDEX_PATH = DEFAULT_VAULT_ROOT / "indices" / "scotus_case_citation_index.json"
DEFAULT_REPORT_PATH = DEFAULT_VAULT_ROOT / "indices" / "scotus_unresolved_anchor_resolution_report.json"
US_CITATION_RE = re.compile(r"\b\d+\s*U\.?\s*S\.?\s*[0-9_]+\b", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve unresolved SCOTUS citation anchors using local vault index only.")
    parser.add_argument("--vault-root", type=Path, default=DEFAULT_VAULT_ROOT, help="Path to precedent_vault")
    parser.add_argument("--index-path", type=Path, default=DEFAULT_INDEX_PATH, help="Path to scotus_case_citation_index.json")
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH, help="Output report path")
    parser.add_argument("--dry-run", action="store_true", help="Do not modify case notes")
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


def _write_note(path: Path, frontmatter: dict[str, Any], body: str) -> None:
    frontmatter_text = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip()
    note_body = body if body.endswith("\n") else f"{body}\n"
    path.write_text(f"---\n{frontmatter_text}\n---\n{note_body}", encoding="utf-8")


def _normalize_us_citation(value: str) -> str:
    normalized = normalize_citation(str(value or ""))
    return normalized if US_CITATION_RE.search(normalized) else ""


def _load_unique_map(index_path: Path) -> dict[str, str]:
    if not index_path.exists():
        return {}
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    unique_map = payload.get("unique_map") if isinstance(payload, dict) else {}
    if not isinstance(unique_map, dict):
        return {}
    out: dict[str, str] = {}
    for raw_cite, case_id in unique_map.items():
        citation = _normalize_us_citation(str(raw_cite or ""))
        if citation and case_id:
            out[citation] = str(case_id)
    return out


def _load_local_alias_map(vault_root: Path) -> dict[str, str]:
    writer = VaultWriter(vault_root)
    local_map = writer.load_existing_case_citation_map()
    out: dict[str, str] = {}
    for raw_cite, case_id in local_map.items():
        citation = _normalize_us_citation(str(raw_cite or ""))
        if citation and case_id:
            out[citation] = str(case_id)
    return out


def main() -> None:
    args = parse_args()
    vault_root = args.vault_root.expanduser().resolve()
    index_path = args.index_path.expanduser().resolve()
    report_path = args.report_path.expanduser().resolve()
    cases_root = vault_root / "cases" / "scotus"

    unique_map = _load_unique_map(index_path)
    local_alias_map = _load_local_alias_map(vault_root)
    unresolved_counts: Counter[str] = Counter()
    note_payloads: list[tuple[Path, dict[str, Any], str]] = []

    for path in sorted(cases_root.rglob("*.md")):
        try:
            raw = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        frontmatter_text, body = _split_frontmatter(raw)
        if not frontmatter_text.strip():
            continue
        try:
            frontmatter = yaml.safe_load(frontmatter_text) or {}
        except Exception:
            continue
        if not isinstance(frontmatter, dict):
            continue
        anchors = frontmatter.get("citation_anchors")
        if not isinstance(anchors, list):
            continue
        for anchor in anchors:
            if not isinstance(anchor, dict):
                continue
            citation = _normalize_us_citation(str(anchor.get("normalized_text") or anchor.get("raw_text") or ""))
            if not citation:
                continue
            current = str(anchor.get("resolved_case_id") or "").strip()
            if current and not current.startswith("courtlistener."):
                continue
            unresolved_counts[citation] += 1
        note_payloads.append((path, frontmatter, body))

    resolution_map: dict[str, tuple[str, str, float]] = {}
    local_resolved = 0
    remaining = []
    for citation, _freq in unresolved_counts.most_common():
        case_id = unique_map.get(citation)
        source_name = "local_index"
        confidence = 0.95
        if not case_id:
            case_id = local_alias_map.get(citation)
            source_name = "local_alias_map"
            confidence = 0.85
        if case_id:
            resolution_map[citation] = (case_id, source_name, confidence)
            local_resolved += 1
        else:
            remaining.append(citation)

    files_changed = 0
    anchors_updated = 0
    unresolved_after = 0
    for path, frontmatter, body in note_payloads:
        anchors = frontmatter.get("citation_anchors")
        if not isinstance(anchors, list):
            continue
        changed = False
        for anchor in anchors:
            if not isinstance(anchor, dict):
                continue
            citation = _normalize_us_citation(str(anchor.get("normalized_text") or anchor.get("raw_text") or ""))
            if not citation:
                continue
            current = str(anchor.get("resolved_case_id") or "").strip()
            needs_update = (not current) or current.startswith("courtlistener.")
            mapped = resolution_map.get(citation)
            if not needs_update:
                continue
            if not mapped:
                unresolved_after += 1
                continue
            anchor["resolved_case_id"] = mapped[0]
            try:
                prior_conf = float(anchor.get("confidence") or 0.0)
            except Exception:
                prior_conf = 0.0
            anchor["confidence"] = max(prior_conf, float(mapped[2]))
            changed = True
            anchors_updated += 1

        if changed:
            files_changed += 1
            if not args.dry_run:
                _write_note(path, frontmatter, body)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "vault_root": str(vault_root),
        "index_path": str(index_path),
        "dry_run": bool(args.dry_run),
        "unresolved_unique_before": len(unresolved_counts),
        "unresolved_anchor_instances_before": int(sum(unresolved_counts.values())),
        "local_index_unique_resolved": local_resolved,
        "remaining_unique_unresolved_after_local_lookup": len(remaining),
        "resolved_unique_total": len(resolution_map),
        "files_changed": files_changed,
        "anchors_updated": anchors_updated,
        "unresolved_anchor_instances_after": unresolved_after,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
