#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml

from acquittify.paths import PRECEDENT_VAULT_ROOT

DEFAULT_CASES_ROOT = PRECEDENT_VAULT_ROOT / "cases" / "scotus"
DEFAULT_REPORT_PATH = PRECEDENT_VAULT_ROOT / "indices" / "scotus_case_dedupe_report.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deduplicate SCOTUS case notes by shared sources.opinion_url.")
    parser.add_argument("--cases-root", type=Path, default=DEFAULT_CASES_ROOT, help="Path to precedent_vault/cases/scotus")
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH, help="JSON report output path")
    parser.add_argument("--dry-run", action="store_true", help="Do not delete files; only report actions")
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


def _normalize_citation(value: str) -> str:
    compact = re.sub(r"\s+", " ", str(value or "").strip())
    if not compact:
        return ""
    compact = re.sub(r"\bU\.\s*S\.\b", "U.S.", compact, flags=re.IGNORECASE)
    compact = re.sub(r"\bU\.?\s*S\.?\b", "U.S.", compact, flags=re.IGNORECASE)
    return compact


def _case_id_quality(case_id: str) -> tuple[int, int]:
    token = str(case_id or "").split(".")[-1].lower()
    score = 0
    if re.search(r"\d+us\d+$", token):
        score += 3
    elif "us" in token:
        score += 2
    if re.search(r"[a-z]", token):
        score += 1
    if re.fullmatch(r"\d+", token):
        score -= 1
    return (score, len(token))


def _selection_score(case_id: str, primary_citation: str, case_summary: str, citation_anchor_count: int) -> tuple[int, tuple[int, int]]:
    score = 0
    primary = _normalize_citation(primary_citation)
    if case_summary:
        score += 2
    if citation_anchor_count > 0:
        score += 2
    if "-" in primary:
        score += 2
    if re.search(r"\b200\s+U\.?\s*S\.?\s+321\b", primary, flags=re.IGNORECASE):
        score -= 4
    return (score, _case_id_quality(case_id))


def _load_case_record(path: Path) -> dict[str, Any] | None:
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None

    frontmatter_text, _ = _split_frontmatter(raw)
    if not frontmatter_text.strip():
        return None
    try:
        payload = yaml.safe_load(frontmatter_text) or {}
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None

    case_id = str(payload.get("case_id") or "").strip()
    source_map = payload.get("sources")
    sources = source_map if isinstance(source_map, dict) else {}
    opinion_url = str(sources.get("opinion_url") or "").strip()
    primary_citation = str(sources.get("primary_citation") or "").strip()
    case_summary = str(payload.get("case_summary") or "").strip()
    anchors = payload.get("citation_anchors")
    anchor_count = len(anchors) if isinstance(anchors, list) else 0

    if not case_id or not opinion_url:
        return None

    return {
        "path": str(path),
        "case_id": case_id,
        "opinion_url": opinion_url,
        "primary_citation": primary_citation,
        "case_summary": case_summary,
        "citation_anchor_count": anchor_count,
        "score": _selection_score(case_id, primary_citation, case_summary, anchor_count),
    }


def main() -> None:
    args = parse_args()
    cases_root = args.cases_root.expanduser().resolve()
    if not cases_root.exists():
        raise FileNotFoundError(f"Cases root not found: {cases_root}")

    by_opinion_url: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(cases_root.rglob("*.md")):
        record = _load_case_record(path)
        if not record:
            continue
        by_opinion_url.setdefault(record["opinion_url"], []).append(record)

    duplicate_groups = []
    delete_paths: list[Path] = []
    for opinion_url, records in sorted(by_opinion_url.items()):
        if len(records) <= 1:
            continue
        ordered = sorted(records, key=lambda item: item["score"], reverse=True)
        keep = ordered[0]
        remove = ordered[1:]
        duplicate_groups.append(
            {
                "opinion_url": opinion_url,
                "keep": keep,
                "remove": remove,
            }
        )
        for item in remove:
            delete_paths.append(Path(item["path"]))

    removed_count = 0
    if not args.dry_run:
        for path in delete_paths:
            if not path.exists():
                continue
            path.unlink()
            removed_count += 1

    report = {
        "cases_root": str(cases_root),
        "dry_run": bool(args.dry_run),
        "duplicate_group_count": len(duplicate_groups),
        "remove_candidate_count": len(delete_paths),
        "removed_count": removed_count,
        "groups": duplicate_groups,
    }
    report_path = args.report_path.expanduser().resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("duplicate_group_count", "remove_candidate_count", "removed_count", "dry_run")}, indent=2))
    print(f"report_json={report_path}")


if __name__ == "__main__":
    main()
