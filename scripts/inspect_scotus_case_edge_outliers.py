#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
from typing import Any

import yaml

from acquittify.metadata_extract import normalize_citation
from acquittify.ontology.citation_extract import extract_citation_mentions
from acquittify.ontology.citation_roles import classify_citation_roles
from acquittify.ontology.vault_writer import VaultWriter
from acquittify.paths import PRECEDENT_VAULT_ROOT

DEFAULT_VAULT_ROOT = PRECEDENT_VAULT_ROOT
DEFAULT_REPORT_PATH = DEFAULT_VAULT_ROOT / "indices" / "scotus_case_edge_outlier_report.json"
DEFAULT_QUEUE_PATH = DEFAULT_VAULT_ROOT / "indices" / "case_edge_outlier_review_queue.md"
US_CITATION_TEXT = "U.S."


@dataclass
class CaseEdgeRecord:
    path: Path
    case_id: str
    title: str
    edge_count: int
    targets: set[str]
    frontmatter: dict[str, Any]
    body: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detect SCOTUS case-edge outliers, perform second-pass rescans, and queue unresolved anomalies."
    )
    parser.add_argument("--vault-root", type=Path, default=DEFAULT_VAULT_ROOT, help="Path to precedent_vault")
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH, help="Output JSON report")
    parser.add_argument("--queue-path", type=Path, default=DEFAULT_QUEUE_PATH, help="Output Markdown user queue")
    parser.add_argument("--dry-run", action="store_true", help="Do not persist frontmatter updates")
    return parser.parse_args()


def _split_frontmatter(raw_text: str) -> tuple[dict[str, Any], str]:
    text = raw_text or ""
    if not text.startswith("---\n"):
        return {}, text
    marker = "\n---\n"
    end = text.find(marker, 4)
    if end == -1:
        return {}, text
    frontmatter_text = text[4:end]
    body = text[end + len(marker) :]
    try:
        payload = yaml.safe_load(frontmatter_text) or {}
    except Exception:
        payload = {}
    return payload if isinstance(payload, dict) else {}, body


def _write_note(path: Path, frontmatter: dict[str, Any], body: str) -> None:
    serialized = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip()
    note_body = body if body.endswith("\n") else f"{body}\n"
    path.write_text(f"---\n{serialized}\n---\n{note_body}", encoding="utf-8")


def _opinion_text(frontmatter: dict[str, Any], body: str) -> str:
    sources = frontmatter.get("sources") if isinstance(frontmatter.get("sources"), dict) else {}
    opinion_url = Path(str((sources or {}).get("opinion_url") or "").strip()).expanduser()
    if opinion_url.exists() and opinion_url.is_file():
        try:
            return opinion_url.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            pass
    return body


def _role_map(opinion_text: str, mentions: list) -> dict[str, str]:
    assignments = classify_citation_roles(opinion_text, mentions) if mentions else []
    roles: dict[str, tuple[str, float]] = {}
    for item in assignments:
        mention = getattr(item, "mention", None)
        normalized = normalize_citation(
            str(getattr(mention, "normalized_text", "") or getattr(mention, "raw_text", "")).strip()
        )
        if not normalized:
            continue
        role = str(getattr(item, "role", "persuasive"))
        if "." in role:
            role = role.split(".")[-1]
        confidence = float(getattr(item, "confidence", 0.0) or 0.0)
        existing = roles.get(normalized)
        if existing is None or confidence > existing[1]:
            roles[normalized] = (role, confidence)
    return {key: value[0] for key, value in roles.items()}


def _build_anchor_entries(
    mentions: list,
    case_id: str,
    local_case_citation_map: dict[str, str],
    role_map: dict[str, str],
) -> list[dict[str, Any]]:
    anchors: list[dict[str, Any]] = []
    seen: set[tuple[int, int, str, str]] = set()
    for mention in mentions:
        normalized = normalize_citation(
            str(getattr(mention, "normalized_text", "") or getattr(mention, "raw_text", "")).strip()
        )
        if not normalized or US_CITATION_TEXT not in normalized:
            continue
        resolved_case_id = str(local_case_citation_map.get(normalized) or "").strip()
        if resolved_case_id == case_id:
            continue
        start_char = int(getattr(mention, "start_char", 0) or 0)
        end_char = int(getattr(mention, "end_char", start_char) or start_char)
        key = (start_char, end_char, normalized, resolved_case_id)
        if key in seen:
            continue
        seen.add(key)
        anchors.append(
            {
                "raw_text": str(getattr(mention, "raw_text", "") or normalized),
                "normalized_text": normalized,
                "resolved_case_id": resolved_case_id or None,
                "confidence": 0.95 if resolved_case_id else 0.0,
                "start_char": start_char,
                "end_char": end_char,
                "role": role_map.get(normalized),
            }
        )
    anchors.sort(
        key=lambda item: (
            int(item.get("start_char") or 0),
            int(item.get("end_char") or 0),
            str(item.get("normalized_text") or ""),
        )
    )
    return anchors


def _quantile(values: list[int], q: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    ranked = sorted(values)
    idx = (len(ranked) - 1) * q
    lower = int(idx)
    upper = min(lower + 1, len(ranked) - 1)
    fraction = idx - lower
    return float(ranked[lower] + (ranked[upper] - ranked[lower]) * fraction)


def _edge_targets(frontmatter: dict[str, Any], case_id: str) -> set[str]:
    targets: set[str] = set()
    anchors = frontmatter.get("citation_anchors")
    if isinstance(anchors, list):
        for item in anchors:
            if not isinstance(item, dict):
                continue
            target = str(item.get("resolved_case_id") or "").strip()
            if target and target != case_id:
                targets.add(target)

    interpretive_edges = frontmatter.get("interpretive_edges")
    if isinstance(interpretive_edges, list):
        for item in interpretive_edges:
            if not isinstance(item, dict):
                continue
            target = str(item.get("target_case_id") or "").strip()
            if target and target != case_id:
                targets.add(target)
    return targets


def _load_case_records(vault_root: Path) -> list[CaseEdgeRecord]:
    records: list[CaseEdgeRecord] = []
    cases_root = vault_root / "cases" / "scotus"
    for path in sorted(cases_root.rglob("*.md")):
        try:
            raw = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        frontmatter, body = _split_frontmatter(raw)
        if not frontmatter:
            continue
        case_id = str(frontmatter.get("case_id") or "").strip()
        if not case_id:
            continue
        title = str(frontmatter.get("title") or "").strip() or case_id
        targets = _edge_targets(frontmatter, case_id)
        records.append(
            CaseEdgeRecord(
                path=path,
                case_id=case_id,
                title=title,
                edge_count=len(targets),
                targets=targets,
                frontmatter=frontmatter,
                body=body,
            )
        )
    return records


def _thresholds(edge_counts: list[int]) -> dict[str, float]:
    if not edge_counts:
        return {
            "mean": 0.0,
            "median": 0.0,
            "stddev": 0.0,
            "q1": 0.0,
            "q3": 0.0,
            "iqr": 0.0,
            "high_threshold": 0.0,
            "low_threshold": 0.0,
        }
    mean_val = statistics.fmean(edge_counts)
    median_val = statistics.median(edge_counts)
    stddev_val = statistics.pstdev(edge_counts) if len(edge_counts) > 1 else 0.0
    q1 = _quantile(edge_counts, 0.25)
    q3 = _quantile(edge_counts, 0.75)
    iqr = max(0.0, q3 - q1)
    high_threshold = max(q3 + 1.5 * iqr, mean_val + 3.0 * stddev_val)
    low_threshold = max(0.0, min(q1 - 1.5 * iqr, mean_val - 3.0 * stddev_val))
    return {
        "mean": float(mean_val),
        "median": float(median_val),
        "stddev": float(stddev_val),
        "q1": float(q1),
        "q3": float(q3),
        "iqr": float(iqr),
        "high_threshold": float(high_threshold),
        "low_threshold": float(low_threshold),
    }


def _write_queue(path: Path, unresolved_items: list[dict[str, Any]], stats: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# Case Edge Outlier Review Queue")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append("")
    lines.append("## Dataset Stats")
    lines.append("")
    lines.append(f"- Cases scanned: {stats.get('cases_scanned', 0)}")
    lines.append(f"- Mean edges per case: {stats.get('mean', 0.0):.3f}")
    lines.append(f"- Median edges per case: {stats.get('median', 0.0):.3f}")
    lines.append(f"- High outlier threshold: {stats.get('high_threshold', 0.0):.3f}")
    lines.append(f"- Low outlier threshold: {stats.get('low_threshold', 0.0):.3f}")
    lines.append("")
    lines.append("## Needs User Review")
    lines.append("")
    if not unresolved_items:
        lines.append("- None.")
    else:
        for item in unresolved_items:
            lines.append(
                f"- [ ] {item['title']} (`{item['case_id']}`): "
                f"{item['old_count']} -> {item['rescanned_count']} edges ({item['reason']})"
            )
            lines.append(f"  - File: `{item['path']}`")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    vault_root = args.vault_root.expanduser().resolve()
    report_path = args.report_path.expanduser().resolve()
    queue_path = args.queue_path.expanduser().resolve()

    writer = VaultWriter(vault_root)
    local_case_citation_map = writer.load_existing_case_citation_map()
    records = _load_case_records(vault_root)
    edge_counts = [item.edge_count for item in records]
    threshold = _thresholds(edge_counts)
    median_edges = float(threshold.get("median", 0.0))
    high_threshold = float(threshold.get("high_threshold", 0.0))
    low_threshold = float(threshold.get("low_threshold", 0.0))

    outliers: list[tuple[str, CaseEdgeRecord]] = []
    for item in records:
        if item.edge_count > high_threshold:
            outliers.append(("high", item))
            continue
        if item.edge_count < low_threshold:
            outliers.append(("low", item))
            continue
        if median_edges >= 3 and item.edge_count == 0:
            outliers.append(("low_zero", item))

    changed_files = 0
    resolved_outliers = 0
    unresolved_outliers = 0
    unresolved_items: list[dict[str, Any]] = []
    outlier_samples: list[dict[str, Any]] = []

    for outlier_type, item in outliers:
        opinion_text = _opinion_text(item.frontmatter, item.body)
        full_mentions = extract_citation_mentions(opinion_text)
        role_map = _role_map(opinion_text, full_mentions)
        rescanned_anchors = _build_anchor_entries(
            mentions=full_mentions,
            case_id=item.case_id,
            local_case_citation_map=local_case_citation_map,
            role_map=role_map,
        )
        rescanned_targets = {
            str(anchor.get("resolved_case_id") or "").strip()
            for anchor in rescanned_anchors
            if str(anchor.get("resolved_case_id") or "").strip() and str(anchor.get("resolved_case_id") or "").strip() != item.case_id
        }
        rescanned_count = len(rescanned_targets)

        if outlier_type == "high":
            resolved = rescanned_count <= high_threshold
            reason = "high_edge_count_persists_after_full_rescan" if not resolved else "resolved_after_full_rescan"
        else:
            target_floor = max(1.0, low_threshold)
            resolved = rescanned_count >= target_floor
            reason = "low_edge_count_persists_after_full_rescan" if not resolved else "resolved_after_full_rescan"

        source_map = item.frontmatter.get("sources") if isinstance(item.frontmatter.get("sources"), dict) else {}
        source_map = dict(source_map)
        source_map["anchor_citation_scope"] = "full_opinion_outlier_rescan"
        item.frontmatter["sources"] = source_map
        item.frontmatter["citation_anchors"] = rescanned_anchors
        item.frontmatter["citations_in_text"] = sorted(
            {
                normalize_citation(str(getattr(mention, "normalized_text", "") or getattr(mention, "raw_text", "")).strip())
                for mention in full_mentions
                if normalize_citation(str(getattr(mention, "normalized_text", "") or getattr(mention, "raw_text", "")).strip())
            }
        )

        if not args.dry_run:
            _write_note(item.path, item.frontmatter, item.body)
            changed_files += 1

        if resolved:
            resolved_outliers += 1
        else:
            unresolved_outliers += 1
            unresolved_items.append(
                {
                    "case_id": item.case_id,
                    "title": item.title,
                    "path": str(item.path),
                    "old_count": item.edge_count,
                    "rescanned_count": rescanned_count,
                    "type": outlier_type,
                    "reason": reason,
                }
            )

        if len(outlier_samples) < 80:
            outlier_samples.append(
                {
                    "case_id": item.case_id,
                    "title": item.title,
                    "path": str(item.path),
                    "type": outlier_type,
                    "old_count": item.edge_count,
                    "rescanned_count": rescanned_count,
                    "resolved": resolved,
                }
            )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "vault_root": str(vault_root),
        "dry_run": bool(args.dry_run),
        "cases_scanned": len(records),
        "edge_stats": threshold,
        "outlier_count": len(outliers),
        "resolved_outliers": resolved_outliers,
        "unresolved_outliers": unresolved_outliers,
        "changed_files": changed_files,
        "outlier_samples": outlier_samples,
        "unresolved_items": unresolved_items[:200],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_queue(
        queue_path,
        unresolved_items=unresolved_items,
        stats={
            "cases_scanned": len(records),
            "mean": threshold.get("mean", 0.0),
            "median": threshold.get("median", 0.0),
            "high_threshold": threshold.get("high_threshold", 0.0),
            "low_threshold": threshold.get("low_threshold", 0.0),
        },
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
