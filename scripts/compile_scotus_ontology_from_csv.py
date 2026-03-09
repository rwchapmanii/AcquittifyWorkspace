#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any

import yaml

from acquittify.ontology.scotus_citation_db import load_scotus_citation_db, CitationMatch
from acquittify.paths import OBSIDIAN_ROOT, PROJECT_ROOT


DEFAULT_CSV_PATH = OBSIDIAN_ROOT / "Ontology" / "supreme_court_case_file_links.csv"
DEFAULT_CITATION_DB = PROJECT_ROOT / "data" / "scdb" / "scotus_citation_db_2011_present.json"
US_CITATION_RE = re.compile(r"\b\d+\s+U\.?\s*S\.?\s+\d+\b")
CITE_AS_LINE_RE = re.compile(r"\bCite\s+as:\s*(\d+\s+U\.?\s*S\.?\s+[0-9_]+)", re.IGNORECASE)
ORDER_SUFFIX_RE = re.compile(r"(?:zor|zr\d*)$", re.IGNORECASE)
CASE_LINE_RE = re.compile(r"\bv\.?\b", re.IGNORECASE)
WHITESPACE_RE = re.compile(r"\s+")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bulk compile SCOTUS ontology artifacts from the SCOTUS ingest CSV.")
    parser.add_argument("--csv-path", type=Path, default=DEFAULT_CSV_PATH, help="Path to supreme_court_case_file_links.csv")
    parser.add_argument("--vault-path", type=Path, default=None, help="SCOTUS vault root. Default: csv_path/../..")
    parser.add_argument(
        "--ontology-vault-root",
        type=Path,
        default=None,
        help="Ontology output root (default: <vault-path>/Ontology/precedent_vault)",
    )
    parser.add_argument(
        "--compile-script",
        type=Path,
        default=Path(__file__).resolve().parent / "compile_precedent_ontology.py",
        help="Path to compile_precedent_ontology.py",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help="Working directory for extracted text and per-case outputs (default: <vault-path>/Ontology/.ontology_compile_work)",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=None,
        help="Summary report path (default: <vault-path>/Ontology/ontology_compile_summary.json)",
    )
    parser.add_argument("--offset", type=int, default=0, help="Start offset after filtering")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of cases to compile after filtering")
    parser.add_argument("--case-id-file", type=Path, default=None, help="Optional JSON file with case_ids list to include")
    parser.add_argument("--include-orders", action="store_true", help="Include order-list style entries (zor/zr)")
    parser.add_argument("--include-nonhyphen-dockets", action="store_true", help="Include case numbers without '-'")
    parser.add_argument("--skip-resolver", action="store_true", help="Pass --skip-resolver to compiler")
    parser.add_argument("--no-run-extractor", action="store_true", help="Skip LLM extraction (metadata-only compile)")
    parser.add_argument(
        "--reuse-existing-case-ids",
        action="store_true",
        help="Reuse legacy case_id values for matching opinion sources (default: recompute local deterministic IDs)",
    )
    parser.add_argument("--max-errors", type=int, default=200, help="Abort run after this many compile failures")
    parser.add_argument("--progress-every", type=int, default=25, help="Print progress every N attempted cases")
    parser.add_argument("--per-case-timeout", type=int, default=300, help="Timeout in seconds for each case compile")
    parser.add_argument(
        "--extract-timeout",
        type=int,
        default=None,
        help="Per-request extractor timeout in seconds (default: per_case_timeout - 20, floor 60)",
    )
    parser.add_argument("--citation-db", type=Path, default=DEFAULT_CITATION_DB, help="Path to SCOTUS citation DB JSON")
    return parser.parse_args()


def _read_csv_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _extract_text_from_note(md_path: Path) -> str:
    text = md_path.read_text(encoding="utf-8", errors="ignore")
    marker = "## Extracted Text"
    idx = text.find(marker)
    if idx == -1:
        return text.strip()
    return text[idx + len(marker) :].strip()


def _split_frontmatter(raw_text: str) -> tuple[str, str]:
    text = raw_text or ""
    if not text.startswith("---\n"):
        return "", text
    marker = "\n---\n"
    end = text.find(marker, 4)
    if end == -1:
        return "", text
    return text[4:end], text[end + len(marker) :]


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
    primary = _normalize_citation_text(primary_citation)
    if case_summary:
        score += 2
    if citation_anchor_count > 0:
        score += 2
    if "-" in primary:
        score += 2
    if re.search(r"\b200\s+U\.?\s*S\.?\s+321\b", primary, flags=re.IGNORECASE):
        score -= 4
    return (score, _case_id_quality(case_id))


def _load_existing_case_id_map(ontology_vault_root: Path) -> dict[str, str]:
    cases_root = ontology_vault_root / "cases" / "scotus"
    if not cases_root.exists():
        return {}

    mapping: dict[str, str] = {}
    score_by_url: dict[str, tuple[int, tuple[int, int]]] = {}
    for path in sorted(cases_root.rglob("*.md")):
        try:
            raw = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        frontmatter_text, _ = _split_frontmatter(raw)
        if not frontmatter_text.strip():
            continue
        try:
            payload = yaml.safe_load(frontmatter_text) or {}
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        case_id = str(payload.get("case_id") or "").strip()
        source_map = payload.get("sources")
        sources = source_map if isinstance(source_map, dict) else {}
        opinion_url = str(sources.get("opinion_url") or "").strip()
        if not case_id or not opinion_url:
            continue
        primary_citation = str(sources.get("primary_citation") or "").strip()
        case_summary = str(payload.get("case_summary") or "").strip()
        anchors = payload.get("citation_anchors")
        anchor_count = len(anchors) if isinstance(anchors, list) else 0
        candidate_score = _selection_score(case_id, primary_citation, case_summary, anchor_count)

        current_score = score_by_url.get(opinion_url)
        if current_score is None or candidate_score > current_score:
            mapping[opinion_url] = case_id
            score_by_url[opinion_url] = candidate_score
    return mapping


def _normalize_citation_text(value: str) -> str:
    compact = re.sub(r"\s+", " ", str(value or "").strip())
    if not compact:
        return ""
    compact = re.sub(r"\bU\.\s*S\.\b", "U.S.", compact, flags=re.IGNORECASE)
    compact = re.sub(r"\bU\.?\s*S\.?\b", "U.S.", compact, flags=re.IGNORECASE)
    return compact


def _looks_like_numeric_reporter_citation(value: str) -> bool:
    return bool(US_CITATION_RE.fullmatch(_normalize_citation_text(value)))


def _infer_primary_citation(extracted_text: str, fallback: str) -> str:
    text = extracted_text or ""
    cite_as_match = CITE_AS_LINE_RE.search(text)
    if cite_as_match:
        cite_as = _normalize_citation_text(cite_as_match.group(1))
        # Skip slip-opinion placeholders like "577 U.S. ____" for ID stability.
        if _looks_like_numeric_reporter_citation(cite_as):
            return cite_as

    # Avoid selecting arbitrary in-text cites (e.g., Detroit Timber in syllabus notes).
    if _looks_like_numeric_reporter_citation(fallback):
        return _normalize_citation_text(fallback)

    candidate = (fallback or "").strip()
    return candidate if candidate else "unknown"


def _looks_like_case_name(raw: str) -> bool:
    value = (raw or "").strip()
    if not value:
        return False
    if "-" in value and " v" not in value.lower():
        return False
    if not CASE_LINE_RE.search(value):
        return False
    normalized = re.sub(r"\s+v\.?\s*", " v. ", value, count=1, flags=re.IGNORECASE)
    left, _, right = normalized.partition(" v. ")
    return bool(re.search(r"[A-Za-z]", left) and re.search(r"[A-Za-z]", right))


def _to_pretty_case_name(raw: str) -> str:
    value = (raw or "").replace("Â", "").replace("\u00a0", " ").strip()
    value = re.sub(r"^\d+\s+", "", value)
    value = re.sub(r"\bet\s*al\.?", "et al.", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+v\.?\s*", " v. ", value, count=1, flags=re.IGNORECASE)
    value = re.sub(r",?\s*PETITIONERS?\b", "", value, flags=re.IGNORECASE)
    value = re.sub(r",?\s*RESPONDENTS?\b", "", value, flags=re.IGNORECASE)
    value = WHITESPACE_RE.sub(" ", value).strip(" ,.;")

    letters = [ch for ch in value if ch.isalpha()]
    uppercase_ratio = (sum(ch.isupper() for ch in letters) / len(letters)) if letters else 0.0
    if uppercase_ratio > 0.55:
        lowers = {"v.", "of", "and", "the", "for", "to", "in", "on", "a", "an", "et", "al."}
        words = value.lower().split()
        rebuilt: list[str] = []
        for idx, word in enumerate(words):
            if idx > 0 and word in lowers:
                rebuilt.append(word)
            else:
                rebuilt.append(word.capitalize())
        value = " ".join(rebuilt)

    value = value.replace(" V. ", " v. ")
    value = value.replace(" Vs. ", " v. ")
    value = re.sub(r"\bet al\.\b", "et al.", value, flags=re.IGNORECASE)
    return WHITESPACE_RE.sub(" ", value).strip(" ,.;")


def _infer_case_name_from_text(extracted_text: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in (extracted_text or "").splitlines()[:260]]
    marker_idx = -1
    for idx, line in enumerate(lines):
        if "SUPREME COURT OF THE UNITED STATES" in line.upper():
            marker_idx = idx
            break
    if marker_idx != -1:
        window = lines[marker_idx + 1 : marker_idx + 28]
        collected: list[str] = []
        for line in window:
            cleaned = re.sub(r"^\d+\s+", "", line).strip()
            if not cleaned:
                if collected:
                    break
                continue
            lowered = cleaned.lower()
            if lowered.startswith(("syllabus", "per curiam", "certiorari", "on petition", "no.", "argued", "decided", "held:")):
                if collected:
                    break
                continue
            if "supreme court" in lowered:
                continue
            if CASE_LINE_RE.search(cleaned):
                collected.append(cleaned)
                continue
            if collected:
                collected.append(cleaned)
                if len(collected) >= 3:
                    break
        if collected:
            joined = re.sub(r"\s+", " ", " ".join(collected)).strip(" ,.;")
            joined = re.split(r"\bON PETITION\b|\bCERTIORARI\b", joined, maxsplit=1, flags=re.IGNORECASE)[0].strip(" ,.;")
            if _looks_like_case_name(joined):
                return joined
    return ""


def _clean_title(caption: str, case_number: str, case_id: str, extracted_text: str) -> str:
    inferred = _infer_case_name_from_text(extracted_text)
    if _looks_like_case_name(inferred):
        return _to_pretty_case_name(inferred)
    caption_val = (caption or "").strip()
    case_number_val = (case_number or "").strip()
    if _looks_like_case_name(caption_val):
        return _to_pretty_case_name(caption_val)
    if caption_val and caption_val.lower() != case_number_val.lower():
        return _to_pretty_case_name(caption_val)
    if case_number_val:
        return case_number_val
    return case_id or "Unknown SCOTUS Case"


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


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _normalize_us_cite(value: str) -> str:
    compact = re.sub(r"\s+", " ", str(value or "").strip())
    compact = re.sub(r"\bU\.\s*S\.\b", "U.S.", compact, flags=re.IGNORECASE)
    compact = re.sub(r"\bU\.?\s*S\.?\b", "U.S.", compact, flags=re.IGNORECASE)
    return compact


def _build_citation_validation(match: CitationMatch | None, db) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    payload: dict[str, Any] = {
        "status": "matched" if match else "unmatched",
        "source": getattr(db, "source", ""),
        "source_url": getattr(db, "source_url", ""),
        "source_version": getattr(db, "version", ""),
        "checked_at": now,
    }
    if match:
        payload.update(
            {
                "match_method": match.match_method,
                "matched_case_id": match.case_id,
                "matched_case_name": match.case_name,
                "matched_decision_date": match.decision_date,
                "matched_citation": match.us_cite,
            }
        )
    return payload


def _update_case_note_metadata(case_path: Path, slip_citation: str, validation: dict[str, Any] | None) -> None:
    if not case_path.exists():
        return
    raw = case_path.read_text(encoding="utf-8", errors="ignore")
    frontmatter_text, body = _split_frontmatter(raw)
    if not frontmatter_text.strip():
        return
    try:
        data = yaml.safe_load(frontmatter_text) or {}
    except Exception:
        return
    if not isinstance(data, dict):
        return
    sources = data.get("sources")
    source_map = sources if isinstance(sources, dict) else {}
    if slip_citation:
        source_map["slip_citation"] = slip_citation
    if validation:
        source_map["citation_validation"] = validation
    data["sources"] = source_map
    frontmatter_out = yaml.safe_dump(data, sort_keys=False, allow_unicode=True).strip()
    note_body = body if body.endswith("\n") else f"{body}\n"
    case_path.write_text(f"---\n{frontmatter_out}\n---\n{note_body}", encoding="utf-8")


def main() -> None:
    args = parse_args()
    csv_path = args.csv_path.expanduser().resolve()
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    vault_path = (args.vault_path.expanduser().resolve() if args.vault_path else csv_path.parent.parent.resolve())
    ontology_vault_root = (
        args.ontology_vault_root.expanduser().resolve()
        if args.ontology_vault_root
        else (vault_path / "Ontology" / "precedent_vault").resolve()
    )
    work_dir = (args.work_dir.expanduser().resolve() if args.work_dir else (vault_path / "Ontology" / ".ontology_compile_work").resolve())
    report_path = (
        args.report_path.expanduser().resolve()
        if args.report_path
        else (vault_path / "Ontology" / "ontology_compile_summary.json").resolve()
    )
    compile_script = args.compile_script.expanduser().resolve()
    if not compile_script.exists():
        raise FileNotFoundError(f"Compiler script not found: {compile_script}")

    rows = _read_csv_rows(csv_path)
    filtered_rows = [row for row in rows if _passes_filters(row, args.include_orders, args.include_nonhyphen_dockets)]

    case_id_allowlist: set[str] | None = None
    if args.case_id_file:
        case_id_path = args.case_id_file.expanduser().resolve()
        if case_id_path.exists():
            payload = json.loads(case_id_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("case_ids"), list):
                case_id_allowlist = {str(item).strip() for item in payload.get("case_ids") if str(item).strip()}
            elif isinstance(payload, list):
                case_id_allowlist = {str(item).strip() for item in payload if str(item).strip()}

    if case_id_allowlist is not None:
        filtered_rows = [row for row in filtered_rows if str(row.get("case_id") or "").strip() in case_id_allowlist]

    existing_case_id_map = _load_existing_case_id_map(ontology_vault_root) if args.reuse_existing_case_ids else {}

    if args.offset > 0:
        filtered_rows = filtered_rows[args.offset :]
    if args.limit is not None:
        filtered_rows = filtered_rows[: max(0, args.limit)]

    work_text_dir = work_dir / "text"
    work_output_dir = work_dir / "outputs"
    work_text_dir.mkdir(parents=True, exist_ok=True)
    work_output_dir.mkdir(parents=True, exist_ok=True)

    run_extractor = not args.no_run_extractor
    start = time.time()

    attempted = 0
    succeeded = 0
    failed = 0
    skipped_missing_note = 0
    changed_total = 0
    holding_total = 0
    issue_total = 0
    relation_total = 0
    source_total = 0
    extraction_error_count = 0
    unresolved_total = 0
    severity_totals = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    reused_case_id_count = 0
    citation_db_matched = 0
    citation_db_unmatched = 0

    failures: list[dict] = []

    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root)
    if args.extract_timeout is not None:
        env["ACQUITTIFY_INGESTION_TIMEOUT"] = str(max(1, int(args.extract_timeout)))
    else:
        env["ACQUITTIFY_INGESTION_TIMEOUT"] = str(max(60, int(args.per_case_timeout) - 20))

    citation_db = load_scotus_citation_db(args.citation_db)

    for row in filtered_rows:
        case_id = (row.get("case_id") or "unknown").strip()
        md_rel = (row.get("md_path") or "").strip()
        md_path = (vault_path / md_rel).resolve()
        if not md_path.exists():
            skipped_missing_note += 1
            continue

        attempted += 1
        extracted_text = _extract_text_from_note(md_path)
        text_path = work_text_dir / f"{case_id}.txt"
        text_path.write_text(extracted_text, encoding="utf-8")

        case_output_path = work_output_dir / f"{case_id}.json"
        decision_date = (row.get("decision_date") or "0000-01-01").strip()
        case_number = (row.get("case_number") or "").strip()
        title = _clean_title(row.get("caption") or "", case_number, case_id, extracted_text)
        slip_candidate = _infer_primary_citation(extracted_text, case_number)
        primary_citation = slip_candidate
        slip_citation = ""
        citation_validation = None
        if citation_db:
            match = citation_db.match(case_number, case_name=title, decision_date=decision_date)
            citation_validation = _build_citation_validation(match, citation_db)
            if match and match.us_cite:
                if _normalize_citation_text(match.us_cite) != _normalize_citation_text(primary_citation):
                    slip_citation = primary_citation
                primary_citation = _normalize_us_cite(match.us_cite)
                citation_db_matched += 1
            else:
                citation_db_unmatched += 1
        pdf_rel = (row.get("pdf_path") or "").strip()
        pdf_abs = (vault_path / pdf_rel).resolve() if pdf_rel else None
        opinion_pdf_path = str(pdf_abs) if pdf_abs and pdf_abs.exists() else ""
        existing_case_id = existing_case_id_map.get(str(text_path))
        if existing_case_id:
            reused_case_id_count += 1

        cmd = [
            sys.executable,
            str(compile_script),
            "--text-file",
            str(text_path),
            "--vault-root",
            str(ontology_vault_root),
            "--title",
            title,
            "--court",
            "SCOTUS",
            "--court-level",
            "supreme",
            "--jurisdiction",
            "US",
            "--date-decided",
            decision_date,
            "--primary-citation",
            primary_citation,
            "--opinion-pdf-path",
            opinion_pdf_path,
            "--output",
            str(case_output_path),
        ]
        # Canonicalize to the local manifest identity (docket-based).
        cmd.extend(["--case-id", case_id])
        if run_extractor:
            cmd.append("--run-extractor")
        if args.skip_resolver:
            cmd.append("--skip-resolver")

        try:
            run = subprocess.run(
                cmd,
                cwd=str(root),
                env=env,
                capture_output=True,
                text=True,
                timeout=max(1, int(args.per_case_timeout)),
            )
        except subprocess.TimeoutExpired:
            failed += 1
            failures.append(
                {
                    "case_id": case_id,
                    "md_path": str(md_path),
                    "returncode": -1,
                    "stderr": f"timeout_after_seconds={int(args.per_case_timeout)}",
                }
            )
            if failed >= args.max_errors:
                break
            continue
        if run.returncode != 0:
            failed += 1
            failures.append(
                {
                    "case_id": case_id,
                    "md_path": str(md_path),
                    "returncode": run.returncode,
                    "stderr": (run.stderr or "").strip()[:2000],
                }
            )
            if failed >= args.max_errors:
                break
            continue

        try:
            payload = json.loads(case_output_path.read_text(encoding="utf-8"))
        except Exception as exc:
            failed += 1
            failures.append(
                {
                    "case_id": case_id,
                    "md_path": str(md_path),
                    "returncode": 0,
                    "stderr": f"output_parse_error: {exc}",
                }
            )
            if failed >= args.max_errors:
                break
            continue

        try:
            write_result = payload.get("write_result") or {}
            case_path = write_result.get("case_path")
            if case_path and (slip_citation or citation_validation):
                _update_case_note_metadata(Path(case_path), slip_citation, citation_validation)
        except Exception:
            pass

        succeeded += 1
        changed_total += int((payload.get("write_result") or {}).get("changed_count") or 0)
        holding_total += int(payload.get("holding_count") or 0)
        issue_total += int(payload.get("issue_count") or 0)
        relation_total += int(payload.get("relation_count") or 0)
        source_total += int(payload.get("source_count") or 0)
        unresolved_total += int(payload.get("unresolved_count") or 0)
        if payload.get("extraction_error"):
            extraction_error_count += 1
        sev = payload.get("unresolved_by_severity") or {}
        for key in ("critical", "high", "medium", "low"):
            severity_totals[key] += int(sev.get(key) or 0)

        if args.progress_every > 0 and attempted % args.progress_every == 0:
            print(
                f"[progress] attempted={attempted} succeeded={succeeded} failed={failed} "
                f"changed_total={changed_total} extraction_errors={extraction_error_count}"
            )

    elapsed = round(time.time() - start, 3)
    report = {
        "csv_path": str(csv_path),
        "vault_path": str(vault_path),
        "ontology_vault_root": str(ontology_vault_root),
        "work_dir": str(work_dir),
        "run_extractor": run_extractor,
        "skip_resolver": bool(args.skip_resolver),
        "reuse_existing_case_ids": bool(args.reuse_existing_case_ids),
        "filters": {
            "include_orders": bool(args.include_orders),
            "include_nonhyphen_dockets": bool(args.include_nonhyphen_dockets),
            "offset": int(args.offset),
            "limit": args.limit,
        },
        "totals": {
            "csv_rows": len(rows),
            "filtered_rows": len(filtered_rows),
            "attempted": attempted,
            "succeeded": succeeded,
            "failed": failed,
            "skipped_missing_note": skipped_missing_note,
            "extraction_error_count": extraction_error_count,
            "changed_total": changed_total,
            "holding_total": holding_total,
            "issue_total": issue_total,
            "relation_total": relation_total,
            "source_total": source_total,
            "unresolved_total": unresolved_total,
            "unresolved_by_severity": severity_totals,
            "reused_case_id_count": reused_case_id_count,
            "citation_db_matched": citation_db_matched,
            "citation_db_unmatched": citation_db_unmatched,
            "elapsed_seconds": elapsed,
        },
        "failures": failures[: min(200, len(failures))],
    }
    _write_json(report_path, report)

    print(json.dumps(report, indent=2, ensure_ascii=False))
    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
