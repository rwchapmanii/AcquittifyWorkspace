#!/usr/bin/env python3
"""Print citation and taxonomy coverage for CAP sample chunks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from acquittify.chunking import chunk_text
from acquittify.ingest.metadata_utils import augment_chunk_metadata
try:
    from taxonomy_embedding_agent import analyze_chunk, build_metadata
except Exception:
    from document_ingestion_backend import analyze_chunk, build_metadata


def _extract_citation_strings(citations) -> list[str]:
    items: list[str] = []
    if isinstance(citations, list):
        for cite in citations:
            value = None
            if isinstance(cite, dict):
                value = cite.get("cite") or cite.get("citation")
            elif isinstance(cite, str):
                value = cite
            else:
                value = str(cite)
            if value:
                items.append(str(value))
    elif isinstance(citations, dict):
        value = citations.get("cite") or citations.get("citation")
        if value:
            items.append(str(value))
    elif isinstance(citations, str):
        items.append(citations)
    return [s.strip() for s in items if str(s).strip()]


def _normalize_court(value) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("name") or value.get("name_abbreviation") or value.get("slug") or value.get("id")
    return None


def _decision_year(decision_date: str | None) -> str | None:
    if not decision_date:
        return None
    text = str(decision_date).strip()
    if len(text) >= 4 and text[:4].isdigit():
        return text[:4]
    return None


def _format_document_citation(case_name: str, cite: str, year: str | None, page: str | None) -> str:
    base = f"{case_name} {cite}" if case_name else cite
    if page:
        base = f"{base}, {page}"
    if year:
        base = f"{base} ({year})"
    return base


def _load_samples(base_dir: Path, limit: int) -> list[tuple[dict, str]]:
    shards_dir = base_dir / "ingest" / "cases"
    samples: list[tuple[dict, str]] = []
    for shard in sorted(shards_dir.glob("cases_*.jsonl")):
        with shard.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                text = record.get("opinion_text") or ""
                if not text.strip():
                    continue
                chunks = chunk_text(text)
                if not chunks:
                    continue
                samples.append((record, chunks[0]))
                if len(samples) >= limit:
                    return samples
    return samples


def main() -> int:
    parser = argparse.ArgumentParser(description="Report CAP citations + taxonomy coverage")
    parser.add_argument("--base-dir", default="acquittify-data", help="Base data directory")
    parser.add_argument("--limit", type=int, default=10, help="Number of samples")
    args = parser.parse_args()

    samples = _load_samples(Path(args.base_dir), args.limit)
    print(f"samples={len(samples)}")

    for idx, (record, chunk) in enumerate(samples, 1):
        taxonomy = analyze_chunk(chunk)
        citation_strings = _extract_citation_strings(record.get("citations"))
        year = _decision_year(record.get("decision_date"))
        page = record.get("page")
        document_citation = None
        if citation_strings:
            document_citation = _format_document_citation(
                record.get("case_name") or record.get("title"),
                citation_strings[0],
                year,
                page,
            )
        meta = build_metadata(record.get("cap_id") or f"cap_{idx}", "cap-static-case-law", 0, taxonomy)
        meta.update(
            {
                "case_name": record.get("case_name") or record.get("title"),
                "court": _normalize_court(record.get("court")),
                "citations": citation_strings,
                "document_citation": document_citation,
                "source_type": "CAP Static Case Law",
                "date": record.get("decision_date"),
            }
        )
        meta = augment_chunk_metadata(meta, chunk)
        if not meta.get("citations"):
            meta["citations"] = _extract_citation_strings(record.get("citations"))
        if not meta.get("document_citation") and meta.get("citations"):
            meta["document_citation"] = meta["citations"][0]

        taxonomy_raw = meta.get("taxonomy")
        taxonomy_parsed: dict = {}
        if isinstance(taxonomy_raw, str) and taxonomy_raw.strip():
            try:
                taxonomy_parsed = json.loads(taxonomy_raw)
            except Exception:
                taxonomy_parsed = {}

        print(f"\n[{idx}] case_name={meta.get('case_name')}")
        print(
            "citation_present="
            f"{bool(meta.get('document_citation'))} "
            f"document_citation={meta.get('document_citation')}"
        )
        print(f"citations={meta.get('citations')}")
        print(f"taxonomy_keys={list(taxonomy_parsed.keys())}")
        for key, values in taxonomy_parsed.items():
            print(f"  {key}: {values}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
