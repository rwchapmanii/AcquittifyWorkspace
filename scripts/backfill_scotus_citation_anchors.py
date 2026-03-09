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
from acquittify.ontology.anchor_scope import extract_citation_mentions_syllabus_first
from acquittify.ontology.citation_extract import extract_citation_mentions
from acquittify.ontology.citation_roles import classify_citation_roles
from acquittify.ontology.vault_writer import VaultWriter
from acquittify.paths import PRECEDENT_VAULT_ROOT, REPORTS_ROOT


DEFAULT_VAULT_ROOT = PRECEDENT_VAULT_ROOT
DEFAULT_REPORT_DIR = REPORTS_ROOT
DEFAULT_INDEX_PATH = DEFAULT_VAULT_ROOT / "indices" / "scotus_case_citation_index.json"
US_CITATION_RE = re.compile(r"\b\d{1,4}\s+U\.?\s*S\.?\s+[0-9_]+\b", re.IGNORECASE)
SYLLABUS_CITATION_MIN_MENTIONS = 4
CASE_CAPTION_RE = re.compile(r"([A-Z][^\\n,;:]{1,120}?\\bv\\.?\\b[^\\n,;:]{1,120})", re.IGNORECASE)
CAPTION_TOKEN_RE = re.compile(r"[a-z0-9]+")
CAPTION_SKIP_TOKENS = {"et", "al", "the", "of", "and", "for", "in", "re", "a", "an", "by"}
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill citation_anchors in SCOTUS case notes using syllabus-first scanning.")
    parser.add_argument("--vault-root", type=Path, default=DEFAULT_VAULT_ROOT, help="Path to precedent_vault")
    parser.add_argument("--index-path", type=Path, default=DEFAULT_INDEX_PATH, help="Path to scotus_case_citation_index.json")
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


def _is_scotus_reporter_citation(value: str) -> bool:
    return bool(US_CITATION_RE.search(str(value or "")))


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


def _load_ambiguous_map(index_path: Path) -> dict[str, list[str]]:
    if not index_path.exists():
        return {}
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    raw = payload.get("ambiguous_map") if isinstance(payload, dict) else {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, list[str]] = {}
    for citation_raw, case_ids_raw in raw.items():
        citation = normalize_citation(str(citation_raw or ""))
        if not citation:
            continue
        if not isinstance(case_ids_raw, list):
            continue
        case_ids = sorted({str(item).strip() for item in case_ids_raw if str(item or "").strip()})
        if len(case_ids) > 1:
            out[citation] = case_ids
    return out


def _load_case_title_index(cases_root: Path) -> dict[str, dict[str, str | tuple[str, str]]]:
    out: dict[str, dict[str, str | tuple[str, str]]] = {}
    for path in sorted(cases_root.rglob("*.md")):
        try:
            raw = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        frontmatter_text, _ = _split_frontmatter(raw)
        if not frontmatter_text.strip():
            continue
        try:
            frontmatter = yaml.safe_load(frontmatter_text) or {}
        except Exception:
            continue
        if not isinstance(frontmatter, dict):
            continue
        case_id = str(frontmatter.get("case_id") or "").strip()
        title = str(frontmatter.get("title") or "").strip()
        decision_date = str(frontmatter.get("date_decided") or "").strip()
        year_match = YEAR_RE.search(decision_date or "")
        decision_year = year_match.group(0) if year_match else ""
        if not case_id or not title:
            continue
        out[case_id] = {
            "normalized_title": _normalize_caption_text(title),
            "signature": _caption_signature(title),
            "decision_year": decision_year,
        }
    return out


def _load_case_title_index_from_index(index_path: Path) -> dict[str, dict[str, str | tuple[str, str]]]:
    if not index_path.exists():
        return {}
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    raw = payload.get("case_aliases") if isinstance(payload, dict) else {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, str | tuple[str, str]]] = {}
    for case_id, data in raw.items():
        if not isinstance(data, dict):
            continue
        normalized_title = str(data.get("normalized_title") or "").strip()
        signature = data.get("signature")
        if isinstance(signature, list):
            signature = tuple(signature)
        if not isinstance(signature, tuple):
            signature = ("", "")
        decision_year = str(data.get("decision_year") or "").strip()
        if not case_id:
            continue
        out[str(case_id)] = {
            "normalized_title": normalized_title,
            "signature": signature,
            "decision_year": decision_year,
        }
    return out


def _context_caption_hint(opinion_text: str, start_char: int, mention_raw: str) -> tuple[tuple[str, str], str]:
    context_start = max(0, int(start_char) - 220)
    context_end = min(len(opinion_text), int(start_char) + 40)
    context = opinion_text[context_start:context_end]
    candidates = []
    match = CASE_CAPTION_RE.search(context)
    if match:
        candidates.append(match.group(1))
    candidates.append(mention_raw)
    candidates.append(context)
    for candidate in candidates:
        signature = _caption_signature(candidate)
        if signature != ("", ""):
            return signature, _normalize_caption_text(candidate)
    return ("", ""), _normalize_caption_text(context)


def _context_year_hint(opinion_text: str, start_char: int) -> str:
    context_start = max(0, int(start_char) - 220)
    context_end = min(len(opinion_text), int(start_char) + 80)
    context = opinion_text[context_start:context_end]
    match = YEAR_RE.search(context)
    return match.group(0) if match else ""


def _resolve_ambiguous_case_id(
    citation: str,
    mention_raw: str,
    start_char: int,
    opinion_text: str,
    ambiguous_map: dict[str, list[str]],
    case_title_index: dict[str, dict[str, str | tuple[str, str]]],
    year_hint: str,
) -> str:
    candidates = ambiguous_map.get(citation) or []
    if not candidates:
        return ""
    signature_hint, normalized_hint = _context_caption_hint(opinion_text, start_char, mention_raw)
    if signature_hint != ("", ""):
        matched = []
        for case_id in candidates:
            item = case_title_index.get(case_id) or {}
            if item.get("signature") == signature_hint:
                matched.append(case_id)
        if len(matched) == 1:
            return matched[0]
    if normalized_hint:
        matched = []
        for case_id in candidates:
            item = case_title_index.get(case_id) or {}
            title_norm = str(item.get("normalized_title") or "")
            if not title_norm:
                continue
            if title_norm in normalized_hint or normalized_hint in title_norm:
                matched.append(case_id)
        if len(matched) == 1:
            return matched[0]
        if len(matched) > 1 and year_hint:
            scored = []
            for case_id in matched:
                item = case_title_index.get(case_id) or {}
                decision_year = str(item.get("decision_year") or "")
                if decision_year and decision_year == year_hint:
                    scored.append(case_id)
            if len(scored) == 1:
                return scored[0]
    return ""


def _resolve_by_case_name(
    mention_raw: str,
    start_char: int,
    opinion_text: str,
    case_title_index: dict[str, dict[str, str | tuple[str, str]]],
) -> str:
    signature_hint, normalized_hint = _context_caption_hint(opinion_text, start_char, mention_raw)
    year_hint = _context_year_hint(opinion_text, start_char)
    candidates = []
    for case_id, meta in case_title_index.items():
        if signature_hint != ("", "") and meta.get("signature") == signature_hint:
            candidates.append(case_id)
            continue
        title_norm = str(meta.get("normalized_title") or "")
        if title_norm and normalized_hint and (title_norm in normalized_hint or normalized_hint in title_norm):
            candidates.append(case_id)

    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1 and year_hint:
        filtered = [case_id for case_id in candidates if str(case_title_index.get(case_id, {}).get("decision_year") or "") == year_hint]
        if len(filtered) == 1:
            return filtered[0]
    return ""


def _build_role_map(role_assignments: list) -> dict[str, str]:
    role_map: dict[str, tuple[str, float]] = {}
    for item in role_assignments:
        normalized = normalize_citation(getattr(item.mention, "normalized_text", "") or getattr(item.mention, "raw_text", ""))
        if not normalized:
            continue
        candidate = (str(item.role.value), float(item.confidence))
        existing = role_map.get(normalized)
        if existing is None or candidate[1] > existing[1]:
            role_map[normalized] = candidate
    return {key: value[0] for key, value in role_map.items()}


def _build_anchor_entries(
    mention_list: list,
    case_id: str,
    opinion_text: str,
    local_case_citation_map: dict[str, str],
    ambiguous_case_citation_map: dict[str, list[str]],
    case_title_index: dict[str, dict[str, str | tuple[str, str]]],
    role_map: dict[str, str],
) -> list[dict[str, Any]]:
    anchors: list[dict[str, Any]] = []
    seen: set[tuple[int, int, str, str]] = set()
    for mention in mention_list:
        normalized = normalize_citation(getattr(mention, "normalized_text", "") or getattr(mention, "raw_text", ""))
        if not normalized or not _is_scotus_reporter_citation(normalized):
            continue
        start_char = int(getattr(mention, "start_char", 0) or 0)
        end_char = int(getattr(mention, "end_char", start_char) or start_char)
        mention_raw = str(getattr(mention, "raw_text", "") or normalized)
        resolved_case_id = str(local_case_citation_map.get(normalized) or "").strip()
        if not resolved_case_id:
            year_hint = _context_year_hint(opinion_text, start_char)
            resolved_case_id = _resolve_ambiguous_case_id(
                citation=normalized,
                mention_raw=mention_raw,
                start_char=start_char,
                opinion_text=opinion_text,
                ambiguous_map=ambiguous_case_citation_map,
                case_title_index=case_title_index,
                year_hint=year_hint,
            )
        if not resolved_case_id:
            resolved_case_id = _resolve_by_case_name(
                mention_raw=mention_raw,
                start_char=start_char,
                opinion_text=opinion_text,
                case_title_index=case_title_index,
            )
        if resolved_case_id == case_id:
            continue
        key = (start_char, end_char, normalized, resolved_case_id)
        if key in seen:
            continue
        seen.add(key)
        anchors.append(
            {
                "raw_text": mention_raw,
                "normalized_text": normalized,
                "resolved_case_id": resolved_case_id or None,
                "confidence": 0.95 if resolved_case_id else 0.0,
                "start_char": start_char,
                "end_char": end_char,
                "role": role_map.get(normalized),
            }
        )
    anchors.sort(key=lambda item: (int(item.get("start_char") or 0), int(item.get("end_char") or 0), str(item.get("normalized_text") or "")))
    return anchors


def _build_citation_payload(
    opinion_text: str,
    case_id: str,
    local_case_citation_map: dict[str, str],
    ambiguous_case_citation_map: dict[str, list[str]],
    case_title_index: dict[str, dict[str, str | tuple[str, str]]],
) -> tuple[list[dict[str, Any]], list[str], str, dict[str, int] | None, int]:
    full_mentions = extract_citation_mentions(opinion_text)
    selected_mentions, scope, syllabus_span = extract_citation_mentions_syllabus_first(
        opinion_text,
        full_mentions=full_mentions,
        min_mentions_for_syllabus=SYLLABUS_CITATION_MIN_MENTIONS,
    )
    role_assignments = classify_citation_roles(opinion_text, full_mentions) if full_mentions else []
    role_map = _build_role_map(role_assignments)

    anchors = _build_anchor_entries(
        mention_list=selected_mentions,
        case_id=case_id,
        opinion_text=opinion_text,
        local_case_citation_map=local_case_citation_map,
        ambiguous_case_citation_map=ambiguous_case_citation_map,
        case_title_index=case_title_index,
        role_map=role_map,
    )
    if scope == "syllabus" and not anchors and full_mentions:
        anchors = _build_anchor_entries(
            mention_list=full_mentions,
            case_id=case_id,
            opinion_text=opinion_text,
            local_case_citation_map=local_case_citation_map,
            ambiguous_case_citation_map=ambiguous_case_citation_map,
            case_title_index=case_title_index,
            role_map=role_map,
        )
        scope = "full_opinion_fallback_no_citation_anchor"
        selected_mentions = full_mentions

    citations_in_text = sorted(
        {
            normalize_citation(getattr(item, "normalized_text", "") or getattr(item, "raw_text", ""))
            for item in full_mentions
            if normalize_citation(getattr(item, "normalized_text", "") or getattr(item, "raw_text", ""))
        }
    )
    span_payload = None
    if syllabus_span is not None:
        span_payload = {
            "start_char": int(syllabus_span.start_char),
            "end_char": int(syllabus_span.end_char),
        }
    return anchors, citations_in_text, scope, span_payload, len(selected_mentions)


def main() -> None:
    args = parse_args()
    vault_root = args.vault_root.expanduser().resolve()
    cases_root = vault_root / "cases" / "scotus"
    report_dir = args.report_dir.expanduser().resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"scotus_citation_anchor_backfill_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.json"

    writer = VaultWriter(vault_root)
    local_case_citation_map = writer.load_existing_case_citation_map()
    index_path = args.index_path.expanduser().resolve()
    ambiguous_case_citation_map = _load_ambiguous_map(index_path)
    case_title_index = _load_case_title_index_from_index(index_path)
    case_title_index.update(_load_case_title_index(cases_root))

    scanned = 0
    changed = 0
    parse_failures = 0
    total_citation_anchors = 0
    scope_counts: Counter[str] = Counter()
    files_changed: list[str] = []
    selected_mention_total = 0

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
            case_id_value = str(frontmatter.get("case_id") or "").strip()
            if case_id_value not in case_id_allowlist:
                continue

        case_id = str(frontmatter.get("case_id") or "").strip()
        if not case_id:
            continue

        opinion_text = _opinion_text_from_frontmatter(frontmatter, body)
        anchors, citations_in_text, scope, span_payload, selected_count = _build_citation_payload(
            opinion_text=opinion_text,
            case_id=case_id,
            local_case_citation_map=local_case_citation_map,
            ambiguous_case_citation_map=ambiguous_case_citation_map,
            case_title_index=case_title_index,
        )
        selected_mention_total += selected_count
        scope_counts[scope] += 1
        total_citation_anchors += len(anchors)

        prior_sources = frontmatter.get("sources") if isinstance(frontmatter.get("sources"), dict) else {}
        source_map = dict(prior_sources) if isinstance(prior_sources, dict) else {}
        if str(source_map.get("anchor_citation_scope") or "") != scope:
            source_map["anchor_citation_scope"] = scope
        if span_payload:
            source_map["anchor_syllabus_span"] = span_payload

        previous_anchors = frontmatter.get("citation_anchors")
        previous_citations = frontmatter.get("citations_in_text")

        if (
            isinstance(previous_anchors, list)
            and previous_anchors == anchors
            and isinstance(previous_citations, list)
            and previous_citations == citations_in_text
            and prior_sources == source_map
        ):
            continue

        frontmatter["citation_anchors"] = anchors
        frontmatter["citations_in_text"] = citations_in_text
        frontmatter["sources"] = source_map
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
        "total_citation_anchors": total_citation_anchors,
        "anchor_scope_counts": dict(sorted(scope_counts.items())),
        "selected_anchor_mentions_total": selected_mention_total,
        "files_changed": files_changed[:80],
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
