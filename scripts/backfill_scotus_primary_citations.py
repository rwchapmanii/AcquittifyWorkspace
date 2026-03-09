#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

import yaml

from acquittify.metadata_extract import normalize_citation
from acquittify.ontology.scotus_citation_db import load_scotus_citation_db
from acquittify.paths import PRECEDENT_VAULT_ROOT, PROJECT_ROOT


DEFAULT_VAULT_ROOT = PRECEDENT_VAULT_ROOT
DEFAULT_REPORT = DEFAULT_VAULT_ROOT / "indices" / "scotus_primary_citation_backfill_report.json"
DEFAULT_CITATION_DB = PROJECT_ROOT / "data" / "scdb" / "scotus_citation_db_2011_present.json"

CITE_AS_RE = re.compile(r"\bCite\s+as:\s*(\d+\s+U\.?\s*S\.?\s+([0-9_]+))", re.IGNORECASE)
NUMERIC_US_RE = re.compile(r"\b(\d+)\s*U\.?\s*S\.?\s*(\d+)\b", re.IGNORECASE)
US_SLIP_RE = re.compile(r"\b(\d+)\s*U\.?\s*S\.?\s*([0-9_]+)\b", re.IGNORECASE)
DOCKET_RE = re.compile(r"^\d{1,2}-\d{1,6}[a-z]*$", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill docket-like primary citations with reporter citations from source notes.")
    parser.add_argument("--vault-root", type=Path, default=DEFAULT_VAULT_ROOT, help="Path to precedent_vault")
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT, help="JSON report path")
    parser.add_argument("--opinion-scan-chars", type=int, default=12000, help="Chars to scan from source note")
    parser.add_argument("--citation-db", type=Path, default=DEFAULT_CITATION_DB, help="Path to SCOTUS citation DB JSON")
    parser.add_argument("--dry-run", action="store_true", help="Do not write files")
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


def _normalize_numeric_us(value: str) -> str:
    normalized = normalize_citation(str(value or ""))
    match = NUMERIC_US_RE.search(normalized)
    if not match:
        return ""
    return f"{int(match.group(1))} U.S. {int(match.group(2))}"


def _normalize_us_or_slip(value: str) -> str:
    normalized = normalize_citation(str(value or ""))
    match = US_SLIP_RE.search(normalized)
    if not match:
        return ""
    volume = str(match.group(1) or "").strip()
    page = str(match.group(2) or "").strip()
    if not volume or not page:
        return ""
    if page.isdigit():
        return f"{int(volume)} U.S. {int(page)}"
    return f"{int(volume)} U.S. {page}"


def _citation_from_text_snippet(text: str, scan_chars: int) -> str:
    snippet = str(text or "")[: max(2000, int(scan_chars))]
    match = CITE_AS_RE.search(snippet)
    if match:
        normalized = _normalize_us_or_slip(match.group(1))
        if normalized:
            return normalized
    generic = US_SLIP_RE.search(snippet)
    if generic:
        normalized = _normalize_us_or_slip(generic.group(0))
        if normalized:
            return normalized
    return ""


def _citation_from_opinion_source(opinion_url: str, scan_chars: int) -> str:
    source = Path(str(opinion_url or "").strip()).expanduser()
    if not source.exists() or not source.is_file():
        return ""
    try:
        text = source.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    return _citation_from_text_snippet(text, scan_chars)


def _citation_from_filename(path: Path) -> str:
    stem = path.stem.replace("Â", " ").replace("_", "_")
    match = US_SLIP_RE.search(stem)
    if not match:
        return ""
    return _normalize_us_or_slip(match.group(0))


def _is_docket_like(value: str) -> bool:
    token = str(value or "").strip()
    if not token:
        return True
    if token.lower() in {"unknown", "unknown citation"}:
        return True
    return bool(DOCKET_RE.fullmatch(token))


def _docket_from_case_id(case_id: str) -> str:
    token = str(case_id or "").strip()
    if token.upper().startswith("SCOTUS-"):
        return token.split("SCOTUS-", 1)[1]
    return token


def _write_note(path: Path, frontmatter: dict[str, Any], body: str) -> None:
    frontmatter_text = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip()
    note_body = body if body.endswith("\n") else f"{body}\n"
    content = f"---\n{frontmatter_text}\n---\n{note_body}"
    path.write_text(content, encoding="utf-8")


def main() -> None:
    args = parse_args()
    vault_root = args.vault_root.expanduser().resolve()
    cases_root = vault_root / "cases" / "scotus"
    citation_db = load_scotus_citation_db(args.citation_db)

    changed_files = 0
    scanned_files = 0
    updated_rows: list[dict[str, str]] = []

    for path in sorted(cases_root.rglob("*.md")):
        scanned_files += 1
        try:
            raw = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        frontmatter_text, body = _split_frontmatter(raw)
        if not frontmatter_text.strip():
            continue
        try:
            data = yaml.safe_load(frontmatter_text) or {}
        except Exception:
            continue
        if not isinstance(data, dict):
            continue

        sources = data.get("sources")
        source_map = sources if isinstance(sources, dict) else {}
        primary = str(source_map.get("primary_citation") or "").strip()
        if not _is_docket_like(primary) and "_" not in primary:
            continue

        reporter = ""
        validation = None
        slip_citation = ""

        if citation_db:
            case_id = str(data.get("case_id") or "").strip()
            title = str(data.get("title") or "").strip()
            decision_date = str(data.get("date_decided") or "").strip()
            docket = _docket_from_case_id(case_id)
            match = citation_db.match(docket, case_name=title, decision_date=decision_date)
            if match and match.us_cite:
                reporter = match.us_cite
                slip_citation = primary if primary and primary != reporter else ""
                validation = {
                    "status": "matched",
                    "source": citation_db.source,
                    "source_url": citation_db.source_url,
                    "source_version": citation_db.version,
                    "match_method": match.match_method,
                    "matched_case_id": match.case_id,
                    "matched_case_name": match.case_name,
                    "matched_decision_date": match.decision_date,
                    "matched_citation": match.us_cite,
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                }
            else:
                validation = {
                    "status": "unmatched",
                    "source": getattr(citation_db, "source", ""),
                    "source_url": getattr(citation_db, "source_url", ""),
                    "source_version": getattr(citation_db, "version", ""),
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                }

        if not reporter:
            opinion_url = str(source_map.get("opinion_url") or "").strip()
            reporter = _citation_from_opinion_source(opinion_url, args.opinion_scan_chars)
            if not reporter:
                reporter = _citation_from_text_snippet(body, args.opinion_scan_chars)
            if not reporter:
                reporter = _citation_from_filename(path)
            if not reporter:
                continue

        if normalize_citation(primary) == normalize_citation(reporter):
            continue

        source_map["primary_citation"] = reporter
        if slip_citation:
            source_map["slip_citation"] = slip_citation
        if validation:
            source_map["citation_validation"] = validation
        data["sources"] = source_map
        changed_files += 1
        updated_rows.append(
            {
                "path": str(path),
                "case_id": str(data.get("case_id") or ""),
                "old_primary_citation": primary,
                "new_primary_citation": reporter,
            }
        )
        if not args.dry_run:
            _write_note(path, data, body)

    report = {
        "vault_root": str(vault_root),
        "cases_root": str(cases_root),
        "dry_run": bool(args.dry_run),
        "scanned_files": scanned_files,
        "changed_files": changed_files,
        "updates": updated_rows,
    }
    report_path = args.report_path.expanduser().resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(
        json.dumps(
            {
                "scanned_files": scanned_files,
                "changed_files": changed_files,
                "dry_run": bool(args.dry_run),
                "report_path": str(report_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
