#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import yaml

from acquittify.ontology.anchor_scope import extract_authority_mentions_syllabus_first
from acquittify.paths import PRECEDENT_VAULT_ROOT, REPORTS_ROOT


DEFAULT_VAULT_ROOT = PRECEDENT_VAULT_ROOT
DEFAULT_REPORT_DIR = REPORTS_ROOT
SYLLABUS_AUTHORITY_MIN_MENTIONS = 3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill authority_anchors in SCOTUS case notes.")
    parser.add_argument("--vault-root", type=Path, default=DEFAULT_VAULT_ROOT, help="Path to precedent_vault")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR, help="Directory for JSON report")
    parser.add_argument("--case-id-file", type=Path, default=None, help="Optional JSON file with case_ids list to include")
    parser.add_argument("--dry-run", action="store_true", help="Compute changes without writing")
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


def _opinion_text_from_frontmatter(frontmatter: dict[str, Any], body: str) -> str:
    source_map = frontmatter.get("sources") if isinstance(frontmatter.get("sources"), dict) else {}
    opinion_url = Path(str(source_map.get("opinion_url") or "").strip()).expanduser()
    if opinion_url.exists() and opinion_url.is_file():
        try:
            return opinion_url.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            pass
    return body


def _build_authority_anchor_payload(opinion_text: str) -> tuple[list[dict[str, Any]], str, dict[str, int] | None]:
    mentions, scope, syllabus_span = extract_authority_mentions_syllabus_first(
        opinion_text,
        min_mentions_for_syllabus=SYLLABUS_AUTHORITY_MIN_MENTIONS,
    )
    payload: list[dict[str, Any]] = []
    for item in mentions:
        payload.append(
            {
                "raw_text": item.raw_text,
                "normalized_text": item.normalized_text,
                "source_id": item.source_id,
                "source_type": item.source_type,
                "confidence": float(item.confidence),
                "start_char": int(item.start_char),
                "end_char": int(item.end_char),
                "extractor": item.extractor,
            }
        )
    span_payload = None
    if syllabus_span is not None:
        span_payload = {
            "start_char": int(syllabus_span.start_char),
            "end_char": int(syllabus_span.end_char),
        }
    return payload, scope, span_payload


def main() -> None:
    args = parse_args()
    vault_root = args.vault_root.expanduser().resolve()
    cases_root = vault_root / "cases" / "scotus"
    report_dir = args.report_dir.expanduser().resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"scotus_authority_anchor_backfill_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.json"

    scanned = 0
    changed = 0
    parse_failures = 0
    total_anchors = 0
    type_counts: Counter[str] = Counter()
    scope_counts: Counter[str] = Counter()
    files_changed: list[str] = []

    case_id_allowlist: set[str] | None = None
    if args.case_id_file:
        case_id_path = args.case_id_file.expanduser().resolve()
        if case_id_path.exists():
            payload = json.loads(case_id_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("case_ids"), list):
                case_id_allowlist = {str(item).strip() for item in payload.get("case_ids") if str(item).strip()}
            elif isinstance(payload, list):
                case_id_allowlist = {str(item).strip() for item in payload if str(item).strip()}

    for path in sorted(cases_root.rglob("*.md")):
        scanned += 1
        raw = path.read_text(encoding="utf-8", errors="ignore")
        frontmatter_text, body = _split_frontmatter(raw)
        if not frontmatter_text.strip():
            continue
        try:
            frontmatter = yaml.safe_load(frontmatter_text) or {}
        except Exception:
            parse_failures += 1
            continue
        if not isinstance(frontmatter, dict):
            continue
        if case_id_allowlist is not None:
            case_id = str(frontmatter.get("case_id") or "").strip()
            if case_id not in case_id_allowlist:
                continue
        opinion_text = _opinion_text_from_frontmatter(frontmatter, body)
        anchors, scope, span_payload = _build_authority_anchor_payload(opinion_text)
        scope_counts[scope] += 1

        previous = frontmatter.get("authority_anchors")
        source_map = frontmatter.get("sources") if isinstance(frontmatter.get("sources"), dict) else {}
        if not isinstance(source_map, dict):
            source_map = {}

        metadata_changed = False
        if str(source_map.get("anchor_authority_scope") or "") != scope:
            source_map["anchor_authority_scope"] = scope
            metadata_changed = True
        if span_payload:
            if source_map.get("anchor_syllabus_span") != span_payload:
                source_map["anchor_syllabus_span"] = span_payload
                metadata_changed = True

        if isinstance(previous, list) and previous == anchors and not metadata_changed:
            for item in anchors:
                source_type = str(item.get("source_type") or "").strip().lower()
                if source_type:
                    type_counts[source_type] += 1
            total_anchors += len(anchors)
            continue

        frontmatter["authority_anchors"] = anchors
        frontmatter["sources"] = source_map
        for item in anchors:
            source_type = str(item.get("source_type") or "").strip().lower()
            if source_type:
                type_counts[source_type] += 1
        total_anchors += len(anchors)
        changed += 1
        files_changed.append(str(path))
        if not args.dry_run:
            _write_note(path, frontmatter, body)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "vault_root": str(vault_root),
        "dry_run": bool(args.dry_run),
        "scanned_files": scanned,
        "changed_files": changed,
        "parse_failures": parse_failures,
        "total_authority_anchors": total_anchors,
        "authority_type_counts": dict(sorted(type_counts.items())),
        "anchor_scope_counts": dict(sorted(scope_counts.items())),
        "files_changed": files_changed[:80],
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
