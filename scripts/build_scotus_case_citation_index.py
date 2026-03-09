#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

import yaml

from acquittify.metadata_extract import normalize_citation
from acquittify.paths import OBSIDIAN_ROOT, PRECEDENT_VAULT_ROOT


DEFAULT_VAULT_ROOT = PRECEDENT_VAULT_ROOT
DEFAULT_OUTPUT = DEFAULT_VAULT_ROOT / "indices" / "scotus_case_citation_index.json"
DEFAULT_CSV_PATH = OBSIDIAN_ROOT / "Ontology" / "supreme_court_case_file_links.csv"

US_CITATION_RE = re.compile(r"\b(\d+)\s*U\.?\s*S\.?\s*([0-9_]+)\b", re.IGNORECASE)
CITE_AS_RE = re.compile(r"\bCite\s+as:\s*(\d+\s+U\.?\s*S\.?\s+([0-9_]+))", re.IGNORECASE)
CAPTION_TOKEN_RE = re.compile(r"[a-z0-9]+")
CAPTION_SKIP_TOKENS = {"et", "al", "the", "of", "and", "for", "in", "re", "a", "an", "by"}
ORDER_SUFFIX_RE = re.compile(r"(?:zor|zr\d*)$", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build canonical SCOTUS citation -> case_id index.")
    parser.add_argument("--vault-root", type=Path, default=DEFAULT_VAULT_ROOT, help="Path to precedent_vault")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output JSON path")
    parser.add_argument("--opinion-scan-chars", type=int, default=12000, help="Chars to scan from opinion source file")
    parser.add_argument("--case-id-file", type=Path, default=None, help="Optional JSON file with case_ids list to include")
    parser.add_argument("--csv-path", type=Path, default=None, help="Optional SCOTUS CSV for source-case indexing")
    parser.add_argument(
        "--source-root",
        type=Path,
        default=None,
        help="Optional root for source case files (default: csv_path/../..)",
    )
    parser.add_argument("--include-orders", action="store_true", help="Include order-list style entries (zor/zr)")
    parser.add_argument("--include-nonhyphen-dockets", action="store_true", help="Include case numbers without '-'")
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


def _read_frontmatter(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {}
    frontmatter_text, _ = _split_frontmatter(raw)
    if not frontmatter_text.strip():
        return {}
    sanitized = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", frontmatter_text)
    try:
        payload = yaml.safe_load(sanitized) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _normalize_caption_text(value: str) -> str:
    text = str(value or "").lower()
    text = text.replace(" vs. ", " v ").replace(" vs ", " v ")
    text = re.sub(r"[^a-z0-9\\s.]", " ", text)
    text = re.sub(r"\\bv\\.\\b", " v ", text)
    text = re.sub(r"\\bv\\b", " v ", text)
    return re.sub(r"\\s+", " ", text).strip()


def _caption_signature(value: str) -> tuple[str, str]:
    normalized = _normalize_caption_text(value)
    if " v " not in normalized:
        return ("", "")
    left, right = normalized.split(" v ", 1)
    left_tokens = [token for token in CAPTION_TOKEN_RE.findall(left) if token not in CAPTION_SKIP_TOKENS]
    right_tokens = [token for token in CAPTION_TOKEN_RE.findall(right) if token not in CAPTION_SKIP_TOKENS]
    if not left_tokens or not right_tokens:
        return ("", "")
    return (left_tokens[0], right_tokens[0])


def _normalize_us_citation(value: str) -> str:
    normalized = normalize_citation(str(value or ""))
    match = US_CITATION_RE.search(normalized)
    if not match:
        return ""
    volume = int(match.group(1))
    page = str(match.group(2) or "").strip()
    if page.isdigit():
        return f"{volume} U.S. {int(page)}"
    if set(page) == {"_"}:
        return f"{volume} U.S. ___"
    return ""


def _citation_from_opinion_source(opinion_url: str, scan_chars: int) -> str:
    source = Path(str(opinion_url or "").strip()).expanduser()
    if not source.exists() or not source.is_file():
        return ""
    try:
        text = source.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    snippet = text[: max(2000, int(scan_chars))]
    match = CITE_AS_RE.search(snippet)
    if not match:
        return ""
    return _normalize_us_citation(match.group(1))


def _citation_from_source_file(path: Path, scan_chars: int) -> str:
    if not path.exists() or not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    snippet = text[: max(2000, int(scan_chars))]
    match = CITE_AS_RE.search(snippet)
    if not match:
        return ""
    return _normalize_us_citation(match.group(1))


def _passes_filters(row: dict[str, str], include_orders: bool, include_nonhyphen: bool) -> bool:
    case_number = (row.get("case_number") or "").strip()
    case_id = (row.get("case_id") or "").strip()
    md_path = (row.get("md_path") or "").strip()
    md_stem = Path(md_path).stem if md_path else ""
    if not include_nonhyphen and "-" not in case_number:
        return False
    if not include_orders:
        tokens = [case_number, case_id, md_stem]
        if any(ORDER_SUFFIX_RE.search(token) for token in tokens if token):
            return False
    if (row.get("pdf_found") or "").strip().lower() != "true":
        return False
    return True


def main() -> None:
    args = parse_args()
    vault_root = args.vault_root.expanduser().resolve()
    cases_root = vault_root / "cases" / "scotus"
    output_path = args.output.expanduser().resolve()

    case_id_allowlist: set[str] | None = None
    if args.case_id_file:
        case_id_path = args.case_id_file.expanduser().resolve()
        if case_id_path.exists():
            payload = json.loads(case_id_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("case_ids"), list):
                case_id_allowlist = {str(item).strip() for item in payload.get("case_ids") if str(item).strip()}
            elif isinstance(payload, list):
                case_id_allowlist = {str(item).strip() for item in payload if str(item).strip()}

    by_citation: dict[str, set[str]] = defaultdict(set)
    by_case_id: dict[str, dict[str, Any]] = {}
    legacy_by_case_id: dict[str, str] = {}
    files_scanned = 0

    if args.csv_path:
        csv_path = args.csv_path.expanduser().resolve()
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV not found: {csv_path}")
        source_root = (
            args.source_root.expanduser().resolve()
            if args.source_root
            else csv_path.parent.parent.resolve()
        )
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        for row in rows:
            if not _passes_filters(row, args.include_orders, args.include_nonhyphen_dockets):
                continue
            case_id = str(row.get("case_id") or "").strip()
            if not case_id:
                continue
            if case_id_allowlist is not None and case_id not in case_id_allowlist:
                continue
            files_scanned += 1
            caption = str(row.get("caption") or "").strip()
            decision_date = str(row.get("decision_date") or "").strip()
            decision_year = re.search(r"(\\d{4})", decision_date or "")
            decision_year = decision_year.group(1) if decision_year else ""
            md_path = str(row.get("md_path") or "").strip()
            source_path = source_root / md_path if md_path else None
            cite_as = _citation_from_source_file(source_path, args.opinion_scan_chars) if source_path else ""

            aliases: set[str] = set()
            normalized = _normalize_us_citation(cite_as)
            if normalized:
                aliases.add(normalized)

            by_case_id[case_id] = {
                "path": str(source_path) if source_path else "",
                "opinion_url": str(source_path) if source_path else "",
                "primary_citation": cite_as,
                "aliases": sorted(aliases),
                "normalized_title": _normalize_caption_text(caption),
                "signature": _caption_signature(caption),
                "decision_year": decision_year,
                "legacy_case_id": "",
            }
            for alias in aliases:
                by_citation[alias].add(case_id)
    else:
        for path in sorted(cases_root.rglob("*.md")):
            files_scanned += 1
            data = _read_frontmatter(path)
            if not data:
                continue

            case_id = str(data.get("case_id") or "").strip()
            if not case_id:
                continue
            if case_id_allowlist is not None and case_id not in case_id_allowlist:
                continue

            sources = data.get("sources") if isinstance(data.get("sources"), dict) else {}
            primary_citation = str(sources.get("primary_citation") or "").strip()
            opinion_url = str(sources.get("opinion_url") or "").strip()
            legacy_case_id = str(sources.get("legacy_case_id") or "").strip()
            title = str(data.get("title") or "").strip()
            decision_date = str(data.get("date_decided") or "").strip()
            decision_year = re.search(r"(\\d{4})", decision_date or "")
            decision_year = decision_year.group(1) if decision_year else ""

            aliases: set[str] = set()
            for candidate in (
                _normalize_us_citation(primary_citation),
                _citation_from_opinion_source(opinion_url, args.opinion_scan_chars),
            ):
                normalized = _normalize_us_citation(candidate)
                if normalized:
                    aliases.add(normalized)

            by_case_id[case_id] = {
                "path": str(path),
                "opinion_url": opinion_url,
                "primary_citation": primary_citation,
                "aliases": sorted(aliases),
                "normalized_title": _normalize_caption_text(title),
                "signature": _caption_signature(title),
                "decision_year": decision_year,
                "legacy_case_id": legacy_case_id,
            }
            if legacy_case_id:
                legacy_by_case_id[case_id] = legacy_case_id
            for alias in aliases:
                by_citation[alias].add(case_id)

    unique_map: dict[str, str] = {}
    ambiguous_map: dict[str, list[str]] = {}
    for citation in sorted(by_citation):
        case_ids = sorted(by_citation[citation])
        if len(case_ids) == 1:
            unique_map[citation] = case_ids[0]
        else:
            ambiguous_map[citation] = case_ids

    legacy_map: dict[str, str] = {}
    ambiguous_legacy_map: dict[str, list[str]] = {}
    for case_id, legacy_id in legacy_by_case_id.items():
        if not legacy_id:
            continue
        existing = legacy_map.get(legacy_id)
        if existing and existing != case_id:
            legacy_map.pop(legacy_id, None)
            ambiguous_legacy_map.setdefault(legacy_id, sorted({existing, case_id}))
            continue
        if legacy_id in ambiguous_legacy_map:
            ambiguous_legacy_map[legacy_id] = sorted(set(ambiguous_legacy_map[legacy_id] + [case_id]))
            continue
        legacy_map[legacy_id] = case_id

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "vault_root": str(vault_root),
        "cases_root": str(cases_root),
        "files_scanned": files_scanned,
        "case_count": len(by_case_id),
        "unique_citation_count": len(unique_map),
        "ambiguous_citation_count": len(ambiguous_map),
        "unique_map": unique_map,
        "ambiguous_map": ambiguous_map,
        "legacy_case_id_map": legacy_map,
        "ambiguous_legacy_case_id_map": ambiguous_legacy_map,
        "case_aliases": by_case_id,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output_path),
                "case_count": len(by_case_id),
                "unique_citation_count": len(unique_map),
                "ambiguous_citation_count": len(ambiguous_map),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
