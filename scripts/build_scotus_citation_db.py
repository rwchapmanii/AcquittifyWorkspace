#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import zipfile
from typing import Any
from urllib.request import urlopen
from io import BytesIO, TextIOWrapper

from acquittify.metadata_extract import normalize_citation
from acquittify.paths import PROJECT_ROOT


DEFAULT_CITATION_URL = "http://scdb.wustl.edu/_brickFiles/2025_01/SCDB_2025_01_caseCentered_Citation.csv.zip"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "scdb" / "scotus_citation_db_2011_present.json"

CASE_NAME_TOKEN_RE = re.compile(r"[a-z0-9]+")
CASE_NAME_SKIP = {"et", "al", "the", "of", "and", "for", "in", "re", "a", "an", "by"}
DOCKET_CLEAN_RE = re.compile(r"[^0-9A-Z-]")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build local SCOTUS citation DB from SCDB case-centered data.")
    parser.add_argument("--citation-url", type=str, default=DEFAULT_CITATION_URL, help="SCDB case-centered citation ZIP URL")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output JSON path")
    parser.add_argument("--min-year", type=int, default=2011, help="Minimum decision year to include")
    parser.add_argument("--max-year", type=int, default=None, help="Maximum decision year to include")
    return parser.parse_args()


def _normalize_docket(value: str) -> str:
    token = str(value or "").strip().upper()
    token = token.replace("NO.", "").replace("NO", "")
    token = token.replace(" ", "")
    token = DOCKET_CLEAN_RE.sub("", token)
    return token


def _normalize_case_name(value: str) -> str:
    text = str(value or "").lower()
    text = text.replace(" vs. ", " v ").replace(" vs ", " v ")
    text = re.sub(r"[^a-z0-9\\s.]", " ", text)
    text = re.sub(r"\\bv\\.\\b", " v ", text)
    text = re.sub(r"\\bv\\b", " v ", text)
    return re.sub(r"\\s+", " ", text).strip()


def _case_name_signature(value: str) -> tuple[str, str]:
    normalized = _normalize_case_name(value)
    if " v " not in normalized:
        return ("", "")
    left, right = normalized.split(" v ", 1)
    left_tokens = [token for token in CASE_NAME_TOKEN_RE.findall(left) if token not in CASE_NAME_SKIP]
    right_tokens = [token for token in CASE_NAME_TOKEN_RE.findall(right) if token not in CASE_NAME_SKIP]
    if not left_tokens or not right_tokens:
        return ("", "")
    return (left_tokens[0], right_tokens[0])


def _normalize_us_cite(value: str) -> str:
    normalized = normalize_citation(str(value or ""))
    if "_" in normalized:
        return ""
    return normalized


def _load_csv_from_zip(url: str) -> list[dict[str, str]]:
    with urlopen(url) as response:
        data = response.read()
    with zipfile.ZipFile(BytesIO(data)) as temp_zip:
        name = next((n for n in temp_zip.namelist() if n.lower().endswith(".csv")), None)
        if not name:
            raise RuntimeError("No CSV found in SCDB ZIP")
        with temp_zip.open(name) as handle:
            reader = csv.DictReader(TextIOWrapper(handle, encoding="utf-8", errors="ignore"))
            return list(reader)


def main() -> None:
    args = parse_args()
    rows = _load_csv_from_zip(args.citation_url)
    if not rows:
        raise RuntimeError("No rows found in SCDB citation dataset")

    by_docket: dict[str, list[dict[str, Any]]] = {}
    by_name_year: dict[str, list[dict[str, Any]]] = {}
    included = 0

    for row in rows:
        decision_date = str(row.get("dateDecision") or "").strip()
        year_match = re.search(r"(19|20)\d{2}", decision_date)
        year = int(year_match.group(0)) if year_match else None
        if year is None or year < int(args.min_year):
            continue
        if args.max_year is not None and year > int(args.max_year):
            continue

        us_cite = _normalize_us_cite(row.get("usCite") or row.get("usCite") or "")
        if not us_cite:
            continue

        case_id = str(row.get("caseId") or "").strip()
        docket = _normalize_docket(row.get("docket") or "")
        case_name = str(row.get("caseName") or "").strip()
        normalized_case_name = _normalize_case_name(case_name)
        signature = _case_name_signature(case_name)

        entry = {
            "case_id": case_id,
            "us_cite": us_cite,
            "case_name": case_name,
            "normalized_case_name": normalized_case_name,
            "signature": signature,
            "decision_date": decision_date,
            "term": str(row.get("term") or "").strip(),
        }
        if docket:
            by_docket.setdefault(docket, []).append(entry)
        if normalized_case_name:
            key = f"{normalized_case_name}|{year}"
            by_name_year.setdefault(key, []).append(entry)

        included += 1

    output = {
        "source": "SCDB_2025_01_caseCentered_Citation",
        "version": "SCDB_2025_01",
        "source_url": args.citation_url,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "min_year": int(args.min_year),
        "max_year": int(args.max_year) if args.max_year is not None else None,
        "records": included,
        "by_docket": by_docket,
        "by_name_year": by_name_year,
    }

    output_path = args.output.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"output": str(output_path), "records": included}, indent=2))


if __name__ == "__main__":
    main()
