#!/usr/bin/env python3
"""Backfill archived local caselaw markdown files into nightly ingest tables."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import psycopg
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import nightly_caselaw_ingest as nightly

DEFAULT_ARCHIVE_DIR = (
    ROOT
    / "_archived_apps"
    / "acquittify_20260303_131259"
    / "acquittifystorage"
    / "corpus"
    / "cases"
    / "Federal Criminal Cases"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill archived markdown cases into nightly caselaw tables")
    parser.add_argument(
        "--db-dsn",
        default=os.getenv("ACQ_CASELAW_DB_DSN") or os.getenv("COURTLISTENER_DB_DSN", ""),
        help="Postgres DSN",
    )
    parser.add_argument(
        "--cases-dir",
        type=Path,
        default=Path(os.getenv("ACQ_CASELAW_ARCHIVE_CASES_DIR", str(DEFAULT_ARCHIVE_DIR))),
        help="Directory containing archived markdown case files",
    )
    parser.add_argument(
        "--taxonomy-path",
        type=Path,
        default=Path(os.getenv("ACQ_CASELAW_TAXONOMY_PATH", str(ROOT / "taxonomy" / "2026.01" / "taxonomy.yaml"))),
    )
    parser.add_argument(
        "--aliases-path",
        type=Path,
        default=Path(os.getenv("ACQ_CASELAW_ALIASES_PATH", str(ROOT / "taxonomy" / "2026.01" / "aliases.yaml"))),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=int(os.getenv("ACQ_CASELAW_ARCHIVE_LIMIT", "0")),
        help="Maximum files to process (0 = all)",
    )
    parser.add_argument(
        "--max-taxonomy-results",
        type=int,
        default=int(os.getenv("ACQ_CASELAW_ARCHIVE_MAX_TAXONOMY_RESULTS", "8")),
    )
    parser.add_argument(
        "--skip-taxonomy-map",
        action="store_true",
        help="Skip full taxonomy matcher and use frontmatter/fallback taxonomy only",
    )
    parser.add_argument(
        "--commit-every",
        type=int,
        default=int(os.getenv("ACQ_CASELAW_ARCHIVE_COMMIT_EVERY", "100")),
        help="Commit interval when writing to DB",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=int(os.getenv("ACQ_CASELAW_ARCHIVE_PROGRESS_EVERY", "200")),
        help="Print progress every N files",
    )
    parser.add_argument(
        "--skip-non-criminal",
        action="store_true",
        help="Skip records that do not classify as criminal or quasi-criminal",
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=Path(os.getenv("ACQ_CASELAW_ARCHIVE_LOG_PATH", str(ROOT / "reports" / "caselaw_archive_backfill.jsonl"))),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
    )
    return parser.parse_args()


def slugify(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower())
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "unknown"


def parse_markdown(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    match = re.match(r"(?s)^---\s*\n(.*?)\n---\s*\n?(.*)$", raw)
    if not match:
        return {}, raw
    frontmatter_raw, body = match.group(1), match.group(2)
    payload = yaml.safe_load(frontmatter_raw) or {}
    if not isinstance(payload, dict):
        payload = {}
    return payload, body


def normalize_citations(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def build_case_id(path: Path, frontmatter: dict[str, Any]) -> str:
    existing = str(frontmatter.get("case_id") or "").strip()
    if existing:
        return existing
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:18]
    return f"case.local.archive.{digest}"


def build_court_id(frontmatter: dict[str, Any], court_name: str) -> str:
    for key in ("originating_circuit", "court_id", "circuit"):
        value = str(frontmatter.get(key) or "").strip().lower()
        if value:
            return value
    return slugify(court_name)


def run() -> dict[str, Any]:
    args = parse_args()
    if not args.db_dsn and not args.dry_run:
        raise SystemExit("Missing --db-dsn (or set ACQ_CASELAW_DB_DSN/COURTLISTENER_DB_DSN)")
    if not args.cases_dir.exists():
        raise SystemExit(f"Cases directory not found: {args.cases_dir}")

    aliases_path = args.aliases_path if args.aliases_path.exists() else None
    taxonomy_version, taxonomy_nodes, taxonomy_catalog = nightly.load_taxonomy_catalog(args.taxonomy_path)

    files = sorted(path for path in args.cases_dir.rglob("*.md") if path.is_file())
    if args.limit > 0:
        files = files[: args.limit]

    started_at = nightly.utc_now()
    ingestion_batch_id = f"local_archive_backfill:{started_at.strftime('%Y%m%dT%H%M%SZ')}"

    summary: dict[str, Any] = {
        "event": "caselaw_archive_backfill_summary",
        "started_at": started_at.isoformat(),
        "finished_at": None,
        "status": "ok",
        "cases_dir": str(args.cases_dir),
        "dry_run": bool(args.dry_run),
        "taxonomy_version": taxonomy_version,
        "ingestion_batch_id": ingestion_batch_id,
        "files_total": len(files),
        "taxonomy_nodes_loaded": 0,
        "scanned": 0,
        "inserted": 0,
        "updated": 0,
        "ontology_units_inserted": 0,
        "ontology_units_updated": 0,
        "skipped_non_criminal": 0,
        "errors": 0,
        "error_samples": [],
    }

    conn = None
    try:
        if args.dry_run:
            conn = psycopg.connect(args.db_dsn) if args.db_dsn else None
        else:
            conn = psycopg.connect(args.db_dsn)

        if conn is not None:
            nightly.CaseStore.init_schema(conn)
            if not args.dry_run:
                summary["taxonomy_nodes_loaded"] = nightly.CaseStore.upsert_taxonomy_nodes(
                    conn,
                    version=taxonomy_version,
                    nodes=taxonomy_nodes,
                    commit=False,
                )
                conn.commit()

        for index, path in enumerate(files, start=1):
            summary["scanned"] += 1
            try:
                frontmatter, body = parse_markdown(path)
                case_id = build_case_id(path, frontmatter)
                case_name = str(frontmatter.get("title") or path.stem).strip()
                court_name = str(frontmatter.get("court") or "Unknown Court").strip()
                court_id = build_court_id(frontmatter, court_name)
                date_filed = nightly.normalize_case_date(str(frontmatter.get("date_decided") or "").strip())
                citations = normalize_citations(frontmatter.get("citations_in_text"))
                docket_number = str(frontmatter.get("docket_number") or "").strip()
                sources = frontmatter.get("sources") if isinstance(frontmatter.get("sources"), dict) else {}
                if not docket_number:
                    docket_number = str(sources.get("docket_number") or "").strip()
                opinion_text = nightly.normalize_opinion_text(body)
                case_summary = str(frontmatter.get("case_summary") or "").strip() or nightly.summarize(opinion_text, 1200)
                essential_holding = str(frontmatter.get("essential_holding") or "").strip() or nightly.summarize(
                    opinion_text, 1800
                )

                case_type, case_type_reason = nightly.classify_case_type(
                    case_name=case_name,
                    docket_number=docket_number,
                    citations=citations,
                    opinion_text=opinion_text,
                )
                if args.skip_non_criminal and not nightly.include_case(case_type, include_quasi_criminal=True):
                    summary["skipped_non_criminal"] += 1
                    continue

                taxonomy_entries = nightly.taxonomy_entries_from_frontmatter(frontmatter, taxonomy_catalog)
                if not taxonomy_entries and not args.skip_taxonomy_map:
                    taxonomy_entries = nightly.map_case_taxonomies(
                        title=case_name,
                        case_summary=case_summary,
                        essential_holding=essential_holding,
                        opinion_text=opinion_text,
                        taxonomy_path=args.taxonomy_path,
                        aliases_path=aliases_path,
                        max_results=max(1, int(args.max_taxonomy_results)),
                    )
                if not taxonomy_entries:
                    taxonomy_entries = nightly.fallback_taxonomy_entries(opinion_text, taxonomy_catalog)
                taxonomy_entries = nightly.dedupe_taxonomy_entries(taxonomy_entries)
                taxonomy_codes = [entry["code"] for entry in taxonomy_entries if entry.get("code")]

                merged_frontmatter = dict(frontmatter)
                merged_frontmatter["type"] = "case"
                merged_frontmatter["case_id"] = case_id
                merged_frontmatter["title"] = case_name
                merged_frontmatter["court"] = court_name
                merged_frontmatter["court_level"] = merged_frontmatter.get("court_level") or nightly.infer_court_level(
                    court_id, court_name
                )
                merged_frontmatter["jurisdiction"] = str(merged_frontmatter.get("jurisdiction") or "US").upper()
                merged_frontmatter["date_decided"] = date_filed
                merged_frontmatter["citations_in_text"] = citations
                merged_frontmatter["case_summary"] = case_summary
                merged_frontmatter["essential_holding"] = essential_holding
                merged_frontmatter["case_taxonomies"] = taxonomy_entries

                merged_sources = dict(sources)
                merged_sources["source"] = merged_sources.get("source") or "local_archive"
                merged_sources["archive_path"] = str(path)
                if citations and not merged_sources.get("primary_citation"):
                    merged_sources["primary_citation"] = citations[0]
                merged_frontmatter["sources"] = merged_sources

                merged_ingestion = (
                    dict(frontmatter.get("ingestion"))
                    if isinstance(frontmatter.get("ingestion"), dict)
                    else {}
                )
                merged_ingestion.update(
                    {
                        "pipeline": "local_archive_backfill",
                        "ingested_at": nightly.utc_now().isoformat(),
                        "taxonomy_version": taxonomy_version,
                        "case_type": case_type,
                        "case_type_reason": case_type_reason,
                    }
                )
                merged_frontmatter["ingestion"] = merged_ingestion

                cluster_id = nightly.synthetic_negative_id(case_id)
                payload = {
                    "case_id": case_id,
                    "courtlistener_cluster_id": cluster_id,
                    "courtlistener_opinion_id": None,
                    "court_id": court_id,
                    "court_name": court_name,
                    "date_filed": date_filed,
                    "docket_number": docket_number,
                    "case_name": case_name,
                    "case_type": case_type if case_type != "non_criminal" else "archived_case",
                    "taxonomy_codes": taxonomy_codes,
                    "taxonomy_version": taxonomy_version,
                    "frontmatter_yaml": nightly.frontmatter_to_yaml(merged_frontmatter),
                    "frontmatter_json": merged_frontmatter,
                    "opinion_text": opinion_text,
                    "opinion_text_sha256": hashlib.sha256(opinion_text.encode("utf-8")).hexdigest() if opinion_text else "",
                    "source_payload": {
                        "archive_path": str(path),
                        "source": "local_archive",
                        "legacy_sources": merged_sources,
                    },
                }

                if args.dry_run:
                    summary["inserted"] += 1
                    summary["ontology_units_inserted"] += len(taxonomy_codes)
                    continue

                status = nightly.CaseStore.upsert_case(conn, payload, commit=False)
                if status == "inserted":
                    summary["inserted"] += 1
                else:
                    summary["updated"] += 1

                source_opinion_id = nightly.resolve_source_opinion_id(
                    opinion_id=payload.get("courtlistener_opinion_id"),
                    cluster_id=payload.get("courtlistener_cluster_id"),
                    case_id=case_id,
                )
                legal_units = nightly.build_legal_unit_payloads(
                    case_id=case_id,
                    taxonomy_codes=taxonomy_codes,
                    taxonomy_version=taxonomy_version,
                    court_id=court_id,
                    court_name=court_name,
                    date_filed=date_filed,
                    frontmatter=merged_frontmatter,
                    opinion_text=opinion_text,
                    source_opinion_id=source_opinion_id,
                    ingestion_batch_id=ingestion_batch_id,
                )
                lu_inserted, lu_updated = nightly.CaseStore.upsert_legal_units(conn, legal_units, commit=False)
                summary["ontology_units_inserted"] += lu_inserted
                summary["ontology_units_updated"] += lu_updated

                if index % max(1, int(args.commit_every)) == 0:
                    conn.commit()
            except Exception as exc:
                summary["errors"] += 1
                if conn is not None and not args.dry_run:
                    conn.rollback()
                if len(summary["error_samples"]) < 20:
                    summary["error_samples"].append(
                        {
                            "path": str(path),
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
                    print(f"[backfill:error] {path}: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            if index % max(1, int(args.progress_every)) == 0:
                print(
                    f"[backfill] scanned={summary['scanned']} inserted={summary['inserted']} "
                    f"updated={summary['updated']} units+={summary['ontology_units_inserted']} "
                    f"errors={summary['errors']}",
                    file=sys.stderr,
                    flush=True,
                )

        if conn is not None and not args.dry_run:
            conn.commit()
    except Exception:
        summary["status"] = "error"
        raise
    finally:
        summary["finished_at"] = nightly.utc_now().isoformat()
        nightly.append_log(args.log_path, summary)
        if conn is not None:
            conn.close()

    return summary


def main() -> int:
    summary = run()
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
