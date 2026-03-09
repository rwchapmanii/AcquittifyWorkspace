#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from acquittify.paths import OBSIDIAN_ROOT, PRECEDENT_VAULT_ROOT

DEFAULT_CSV_PATH = OBSIDIAN_ROOT / "Ontology" / "supreme_court_case_file_links.csv"
DEFAULT_OUTPUT = PRECEDENT_VAULT_ROOT / "indices" / "pilot_100_case_ids.json"
ORDER_SUFFIX_RE = re.compile(r"(?:zor|zr\d*)$", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Select deterministic SCOTUS pilot cases from ingest CSV.")
    parser.add_argument("--csv-path", type=Path, default=DEFAULT_CSV_PATH, help="Path to supreme_court_case_file_links.csv")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output JSON path")
    parser.add_argument("--limit", type=int, default=100, help="Number of cases to select")
    return parser.parse_args()


def _read_csv_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _passes_filters(row: dict[str, str]) -> bool:
    case_number = (row.get("case_number") or "").strip()
    case_id = (row.get("case_id") or "").strip()
    md_path = (row.get("md_path") or "").strip()
    md_stem = Path(md_path).stem if md_path else ""

    if not case_id:
        return False
    if "-" not in case_number:
        return False
    if any(ORDER_SUFFIX_RE.search(token) for token in (case_number, case_id, md_stem) if token):
        return False
    if (row.get("pdf_found") or "").strip().lower() != "true":
        return False
    return True


def _stable_key(value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()
    return digest


def main() -> None:
    args = parse_args()
    csv_path = args.csv_path.expanduser().resolve()
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    rows = _read_csv_rows(csv_path)
    filtered = [row for row in rows if _passes_filters(row)]

    scored: list[tuple[str, dict[str, str]]] = []
    for row in filtered:
        case_id = str(row.get("case_id") or "").strip()
        case_number = str(row.get("case_number") or "").strip()
        seed = f"{case_id}|{case_number}"
        scored.append((_stable_key(seed), row))

    scored.sort(key=lambda item: item[0])
    limit = max(1, int(args.limit))
    selected_rows = [row for _, row in scored[:limit]]

    output_payload = {
        "generated_at": Path(__file__).stat().st_mtime,
        "csv_path": str(csv_path),
        "total_rows": len(rows),
        "filtered_rows": len(filtered),
        "limit": limit,
        "selected_count": len(selected_rows),
        "case_ids": [str(row.get("case_id") or "").strip() for row in selected_rows],
        "selected": [
            {
                "case_id": str(row.get("case_id") or "").strip(),
                "case_number": str(row.get("case_number") or "").strip(),
                "decision_date": str(row.get("decision_date") or "").strip(),
                "md_path": str(row.get("md_path") or "").strip(),
                "pdf_path": str(row.get("pdf_path") or "").strip(),
            }
            for row in selected_rows
        ],
    }

    output_path = args.output.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"output": str(output_path), "selected_count": len(selected_rows)}, indent=2))


if __name__ == "__main__":
    main()
