#!/usr/bin/env python3
"""
Benchmark citation-checker latency and accuracy against the local CAP ingest shards.

Examples:
  python3 scripts/benchmark_citation_checker.py
  python3 scripts/benchmark_citation_checker.py --runs 3 --sample-size 150 --remote
"""

from __future__ import annotations

import argparse
import json
import random
import re
import ssl
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

try:
    import requests  # type: ignore
except Exception:
    requests = None


FEDERAL_CITATION_PATTERN = re.compile(
    r"\b\d{1,4}\s+"
    r"(?:U\.?\s*S\.?|S\.?\s*Ct\.?|L\.?\s*Ed\.?\s*2d|L\.?\s*Ed\.?|"
    r"F\.?\s*Supp\.?\s*3d|F\.?\s*Supp\.?\s*2d|F\.?\s*Supp\.?|"
    r"F\.?\s*App(?:'|’)?x|F\.?\s*4th|F\.?\s*3d|F\.?\s*2d|F\.?)"
    r"(?:\s*\([^)\r\n]{1,80}\))?\s+\d{1,5}\b",
    re.IGNORECASE,
)

FEDERAL_CITATION_HINT_PATTERN = re.compile(
    r"(U\.?\s*S\.?|S\.?\s*Ct\.?|L\.?\s*Ed\.?|F\.?\s*Supp\.?|"
    r"F\.?\s*App(?:'|’)?x|F\.?\s*\d+d|F\.?\s*4th)",
    re.IGNORECASE,
)

COURTLISTENER_SEARCH_URL = "https://www.courtlistener.com/api/rest/v4/search/"


@dataclass
class CitationHit:
    case_name: str
    court: str
    decision_date: str
    source: str


def sanitize_single_line(value: str, max_len: int = 180) -> str:
    compact = re.sub(r"\s+", " ", str(value or "")).strip()
    if not compact:
        return ""
    if len(compact) <= max_len:
        return compact
    return compact[: max(0, max_len - 1)].rstrip() + "..."


def normalize_federal_citation(value: str) -> str:
    text = sanitize_single_line(value, 180)
    if not text:
        return ""

    text = re.sub(r"\bU\s*\.?\s*S\s*\.?", "U.S.", text, flags=re.IGNORECASE)
    text = re.sub(r"\bS\s*\.?\s*Ct\s*\.?", "S. Ct.", text, flags=re.IGNORECASE)
    text = re.sub(r"\bL\s*\.?\s*Ed\s*\.?\s*2d\b", "L. Ed. 2d", text, flags=re.IGNORECASE)
    text = re.sub(r"\bL\s*\.?\s*Ed\s*\.?", "L. Ed.", text, flags=re.IGNORECASE)
    text = re.sub(r"\bF\s*\.?\s*Supp\s*\.?\s*3d\b", "F. Supp. 3d", text, flags=re.IGNORECASE)
    text = re.sub(r"\bF\s*\.?\s*Supp\s*\.?\s*2d\b", "F. Supp. 2d", text, flags=re.IGNORECASE)
    text = re.sub(r"\bF\s*\.?\s*Supp\s*\.?", "F. Supp.", text, flags=re.IGNORECASE)
    text = re.sub(r"\bF\s*\.?\s*App(?:'|’)?x\b", "F. App'x", text, flags=re.IGNORECASE)
    text = re.sub(r"\bF\s*\.?\s*4th\b", "F.4th", text, flags=re.IGNORECASE)
    text = re.sub(r"\bF\s*\.?\s*3d\b", "F.3d", text, flags=re.IGNORECASE)
    text = re.sub(r"\bF\s*\.?\s*2d\b", "F.2d", text, flags=re.IGNORECASE)
    text = re.sub(r"\.{2,}", ".", text)
    text = re.sub(r"\(\s*[^()\r\n]{1,80}\s*\)\s*(?=\d{1,5}\b)", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    match = re.match(r"^(\d{1,4})\s+(.+?)\s+(\d{1,5})$", text)
    if not match:
        return ""

    volume = str(int(match.group(1)))
    reporter = re.sub(r"\s+", " ", match.group(2)).strip()
    page = str(int(match.group(3)))
    if not reporter or reporter.lower() == "f.":
        return ""
    return f"{volume} {reporter} {page}"


def extract_federal_citations_from_input(raw: str) -> List[str]:
    text = str(raw or "")
    collected: List[str] = []

    for match in FEDERAL_CITATION_PATTERN.findall(text):
        normalized = normalize_federal_citation(match)
        if normalized and normalized not in collected:
            collected.append(normalized)
    if collected:
        return collected

    for chunk in re.split(r"[\r\n,;]+", text):
        chunk = sanitize_single_line(chunk, 180)
        if not chunk:
            continue
        if not re.search(r"\d", chunk) or not FEDERAL_CITATION_HINT_PATTERN.search(chunk):
            continue
        normalized = normalize_federal_citation(chunk)
        if normalized and normalized not in collected:
            collected.append(normalized)
    return collected


def normalize_cap_citation_entry(entry) -> str:
    if isinstance(entry, str):
        return normalize_federal_citation(entry)
    if not isinstance(entry, dict):
        return ""
    return normalize_federal_citation(entry.get("cite") or entry.get("citation") or "")


def summarize_local_hit(record: dict) -> CitationHit:
    return CitationHit(
        case_name=sanitize_single_line(
            record.get("case_name") or record.get("name_abbreviation") or record.get("name") or "", 180
        ),
        court=sanitize_single_line(record.get("court") or "", 120),
        decision_date=str(record.get("decision_date") or "").strip(),
        source="cap_local",
    )


def summarize_remote_hit(record: dict) -> CitationHit:
    return CitationHit(
        case_name=sanitize_single_line(record.get("caseName") or record.get("caseNameFull") or "", 180),
        court=sanitize_single_line(
            record.get("court_citation_string") or record.get("court") or record.get("court_id") or "", 120
        ),
        decision_date=str(record.get("dateFiled") or record.get("dateArgued") or "").strip(),
        source="courtlistener",
    )


def resolve_case_files(base_dir: Path) -> List[Path]:
    case_dir = base_dir / "ingest" / "cases"
    if not case_dir.exists():
        return []
    return sorted(case_dir.glob("cases_*.jsonl"))


def build_local_index(case_files: Iterable[Path]) -> Tuple[Dict[str, CitationHit], int, int, float]:
    index: Dict[str, CitationHit] = {}
    scanned_files = 0
    scanned_lines = 0
    started = time.perf_counter()

    for file_path in case_files:
        scanned_files += 1
        with file_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                scanned_lines += 1
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict):
                    continue
                citations = record.get("citations")
                if not isinstance(citations, list) or not citations:
                    continue
                summary = summarize_local_hit(record)
                for raw_cite in citations:
                    normalized = normalize_cap_citation_entry(raw_cite)
                    if not normalized or normalized in index:
                        continue
                    index[normalized] = summary

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return index, scanned_files, scanned_lines, elapsed_ms


def extract_normalized_from_courtlistener_record(record: dict) -> List[str]:
    out: List[str] = []
    citations = record.get("citation")
    if not isinstance(citations, list):
        return out
    for value in citations:
        normalized = normalize_federal_citation(value)
        if normalized and normalized not in out:
            out.append(normalized)
    return out


def lookup_remote_citation(citation: str, timeout_s: int, cache: Dict[str, Optional[CitationHit]]) -> Optional[CitationHit]:
    if citation in cache:
        return cache[citation]

    query = urllib.parse.urlencode(
        {"type": "o", "page_size": "5", "q": f'citation:"{citation}"'}
    )
    url = f"{COURTLISTENER_SEARCH_URL}?{query}"
    payload = None

    if requests is not None:
        try:
            resp = requests.get(url, timeout=timeout_s, headers={"Accept": "application/json"})
            if resp.ok:
                payload = resp.json()
        except Exception:
            payload = None

    if payload is None:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        insecure_context = ssl._create_unverified_context()
        try:
            with urllib.request.urlopen(req, timeout=timeout_s, context=insecure_context) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
            cache[citation] = None
            return None

    for row in payload.get("results") or []:
        if citation in extract_normalized_from_courtlistener_record(row):
            hit = summarize_remote_hit(row)
            cache[citation] = hit
            return hit

    cache[citation] = None
    return None


def run_check(
    input_text: str,
    local_index: Dict[str, CitationHit],
    remote_enabled: bool,
    remote_timeout_s: int,
    remote_cache: Dict[str, Optional[CitationHit]],
    remote_limit: int = 48,
) -> Tuple[List[dict], dict]:
    citations = extract_federal_citations_from_input(input_text)
    rows: List[dict] = []
    remote_checked = 0
    remote_found = 0

    for citation in citations:
        hit = local_index.get(citation)
        if not hit and remote_enabled and remote_checked < remote_limit:
            remote_checked += 1
            hit = lookup_remote_citation(citation, remote_timeout_s, remote_cache)
            if hit:
                remote_found += 1
        rows.append(
            {
                "citation": citation,
                "valid": bool(hit),
                "match": hit,
            }
        )

    stats = {
        "checked": len(rows),
        "valid": sum(1 for row in rows if row["valid"]),
        "invalid": sum(1 for row in rows if not row["valid"]),
        "remoteChecked": remote_checked,
        "remoteFound": remote_found,
    }
    return rows, stats


def metrics(rows: List[dict], expected: Dict[str, bool]) -> dict:
    tp = fp = tn = fn = 0
    for row in rows:
        predicted = bool(row.get("valid"))
        truth = bool(expected.get(row.get("citation"), False))
        if predicted and truth:
            tp += 1
        elif predicted and not truth:
            fp += 1
        elif not predicted and not truth:
            tn += 1
        else:
            fn += 1
    total = tp + fp + tn + fn
    return {
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "accuracy": (tp + tn) / total if total else 0.0,
        "precision": tp / (tp + fp) if (tp + fp) else 0.0,
        "recall": tp / (tp + fn) if (tp + fn) else 0.0,
    }


def benchmark_scenario(
    name: str,
    input_text: str,
    expected: Dict[str, bool],
    local_index: Dict[str, CitationHit],
    runs: int,
    warm: bool,
    remote_enabled: bool,
    remote_timeout_s: int,
) -> dict:
    durations_ms: List[float] = []
    rows_out: List[dict] = []
    stats_out: dict = {}
    remote_cache: Dict[str, Optional[CitationHit]] = {}

    if warm:
        run_check(input_text, local_index, remote_enabled, remote_timeout_s, remote_cache)

    for _ in range(runs):
        if not warm:
            remote_cache.clear()
        started = time.perf_counter()
        rows, stats = run_check(input_text, local_index, remote_enabled, remote_timeout_s, remote_cache)
        durations_ms.append((time.perf_counter() - started) * 1000.0)
        rows_out = rows
        stats_out = stats

    return {
        "name": name,
        "runs": runs,
        "latency_ms": {
            "p50": statistics.median(durations_ms),
            "mean": statistics.mean(durations_ms),
            "min": min(durations_ms),
            "max": max(durations_ms),
        },
        "quality": metrics(rows_out, expected),
        "stats": stats_out,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Acquittify citation checker.")
    parser.add_argument(
        "--base-dir",
        default="acquittify-data",
        help="Path to CAP data base dir (default: acquittify-data).",
    )
    parser.add_argument("--runs", type=int, default=5, help="Runs per benchmark scenario.")
    parser.add_argument("--sample-size", type=int, default=100, help="Valid-citation sample size.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducible sampling.")
    parser.add_argument("--remote", action="store_true", help="Enable CourtListener fallback in benchmark.")
    parser.add_argument("--remote-timeout", type=int, default=9, help="Remote request timeout seconds.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON summary.")
    args = parser.parse_args()

    random.seed(args.seed)
    base_dir = Path(args.base_dir).resolve()
    case_files = resolve_case_files(base_dir)
    if not case_files:
        print(f"No CAP case shards found under {base_dir / 'ingest' / 'cases'}")
        return 1

    local_index, scanned_files, scanned_lines, index_build_ms = build_local_index(case_files)
    valid_pool = [citation for citation in local_index.keys() if FEDERAL_CITATION_PATTERN.fullmatch(citation)]
    if len(valid_pool) < args.sample_size:
        print(f"Need at least {args.sample_size} citations in local index; found {len(valid_pool)}.")
        return 1

    sample_valid = random.sample(valid_pool, args.sample_size)
    sample_invalid = []
    for idx, citation in enumerate(sample_valid):
        match = re.match(r"^(\d+)\s+(.+?)\s+(\d+)$", citation)
        if not match:
            continue
        sample_invalid.append(f"{int(match.group(1))} {match.group(2)} {90000 + idx}")
    mixed_input = "\n".join(sample_valid + sample_invalid)
    mixed_expected = {citation: True for citation in sample_valid}
    for citation in sample_invalid:
        mixed_expected[citation] = False

    user_input = (
        "Marbury v. Madison, 5 U.S. (1 Cranch) 137 (1803).\n\n"
        "Brown v. Board of Education, 347 U.S. 483 (1954).\n\n"
        "Miranda v. Arizona, 384 U.S. 436 (1966).\n\n"
        "Gideon v. Wainwright, 372 U.S. 335 (1963).\n\n"
        "Roe v. Wade, 410 U.S. 113 (1973).\n\n"
        "Dobbs v. Jackson Women's Health Organization, 597 U.S. 215 (2022).\n\n"
        "New York Times Co. v. Sullivan, 376 U.S. 254 (1964).\n\n"
        "United States v. Booker, 543 U.S. 220 (2005).\n\n"
        "Kelo v. City of New London, 545 U.S. 469 (2005).\n\n"
        "Katz v. United States, 389 U.S. 347 (1967).\n\n"
        "Terry v. Ohio, 392 U.S. 14 (1968)."
    )
    user_expected = {
        "5 U.S. 137": True,
        "347 U.S. 483": True,
        "384 U.S. 436": True,
        "372 U.S. 335": True,
        "410 U.S. 113": True,
        "597 U.S. 215": True,
        "376 U.S. 254": True,
        "543 U.S. 220": True,
        "545 U.S. 469": True,
        "389 U.S. 347": True,
        "392 U.S. 14": False,
    }

    results = [
        benchmark_scenario(
            name="Mixed local set (cold)",
            input_text=mixed_input,
            expected=mixed_expected,
            local_index=local_index,
            runs=max(1, args.runs),
            warm=False,
            remote_enabled=False,
            remote_timeout_s=args.remote_timeout,
        ),
        benchmark_scenario(
            name="Mixed local set (warm)",
            input_text=mixed_input,
            expected=mixed_expected,
            local_index=local_index,
            runs=max(1, args.runs),
            warm=True,
            remote_enabled=False,
            remote_timeout_s=args.remote_timeout,
        ),
    ]

    if args.remote:
        results.append(
            benchmark_scenario(
                name="User sample with remote fallback (cold)",
                input_text=user_input,
                expected=user_expected,
                local_index=local_index,
                runs=max(1, args.runs),
                warm=False,
                remote_enabled=True,
                remote_timeout_s=args.remote_timeout,
            )
        )
        results.append(
            benchmark_scenario(
                name="User sample with remote fallback (warm)",
                input_text=user_input,
                expected=user_expected,
                local_index=local_index,
                runs=max(1, args.runs),
                warm=True,
                remote_enabled=True,
                remote_timeout_s=args.remote_timeout,
            )
        )

    summary = {
        "base_dir": str(base_dir),
        "case_shards": len(case_files),
        "index_size": len(local_index),
        "index_scan": {
            "files": scanned_files,
            "lines": scanned_lines,
            "build_ms": index_build_ms,
        },
        "results": results,
    }

    if args.json:
        print(json.dumps(summary, indent=2))
        return 0

    print(f"CAP shard files: {len(case_files)}")
    print(f"Index size: {len(local_index)} citations")
    print(
        f"Index build: files={scanned_files} lines={scanned_lines} "
        f"time_ms={index_build_ms:.1f}"
    )
    for item in results:
        latency = item["latency_ms"]
        quality = item["quality"]
        stats = item["stats"]
        print()
        print(f"=== {item['name']} ===")
        print(
            "latency_ms: "
            f"p50={latency['p50']:.2f} mean={latency['mean']:.2f} "
            f"min={latency['min']:.2f} max={latency['max']:.2f} runs={item['runs']}"
        )
        print(
            "quality: "
            f"accuracy={quality['accuracy']:.3f} precision={quality['precision']:.3f} "
            f"recall={quality['recall']:.3f} tp={quality['tp']} fp={quality['fp']} "
            f"tn={quality['tn']} fn={quality['fn']}"
        )
        print(
            f"check_stats: checked={stats['checked']} valid={stats['valid']} invalid={stats['invalid']} "
            f"remote={stats['remoteFound']}/{stats['remoteChecked']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
