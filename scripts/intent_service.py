#!/usr/bin/env python3
import argparse
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple

import psycopg

DEFAULT_DSN = "postgresql://acquittify@localhost:5432/courtlistener"
TAXONOMY_ROOT = Path(__file__).resolve().parents[1] / "taxonomy"
_UNAVAILABLE_DSN: set[str] = set()

try:
    from scripts.taxonomy_loader import load_taxonomy as load_taxonomy_file
except ModuleNotFoundError:
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from scripts.taxonomy_loader import load_taxonomy as load_taxonomy_file

SUPPRESSION_PATTERNS = [
    r"\bsuppress(?:ion|ed|ing)?\b",
    r"\bexclude\s+evidence\b",
]

# Rule evaluation order is fixed and deterministic.
RULES: List[Tuple[str, str, float, str]] = [
    (r"\bbrady\b", "brady", 0.85, "doctrine"),
    (r"\bgiglio\b", "giglio", 0.8, "doctrine"),
    (r"\bterry\b", "terry", 0.85, "doctrine"),
    (r"\bfranks\b", "franks", 0.85, "doctrine"),
    (r"\bleon\b", "leon", 0.8, "doctrine"),
    (r"\bbooker\b", "booker", 0.8, "doctrine"),
    (r"\brule\s*16\b", "rule 16", 0.6, "context"),
    (r"\brule\s*29\b", "rule 29", 0.6, "context"),
    (r"\brule\s*404\s*\(b\)\b|\b404\(b\)\b", "404(b)", 0.8, "doctrine"),
    (r"\brule\s*403\b|\b403\b|\bunfair prejudice\b", "403", 0.8, "doctrine"),
    (r"\bmiranda\b", "miranda", 0.85, "doctrine"),
    (r"\bsufficiency\b", "sufficiency", 0.6, "context"),
    (r"\btheory of defense\b|\bjury instruction\b", "jury instruction", 0.6, "context"),
    (r"\bguideline\b|\bguidelines\b|\bbase offense level\b", "guideline", 0.6, "context"),
    (r"\bsentenc(?:e|ing)\b", "sentencing", 0.6, "context"),
    (r"\bappeal(?:ed|s|ing)?\b", "appeal", 0.6, "context"),
]

# Posture rules are evaluated in order; first match wins.
POSTURE_RULES: List[Tuple[str, str]] = [
    (r"\b2255\b", "HABEAS_2255"),
    (r"\bappeal(?:ed|s|ing)?\b", "APPEAL"),
    (r"\bsuppress(?:ion|ed|ing)?\b", "SUPPRESSION"),
    (r"\bsentenc(?:e|ing)\b", "SENTENCING"),
]


def get_taxonomy_version_and_nodes(conn, requested_version: str | None) -> tuple[str, list[dict], set[str], dict]:
    with conn.cursor() as cur:
        if requested_version:
            cur.execute(
                "SELECT DISTINCT version FROM derived.taxonomy_node WHERE version = %s",
                (requested_version,),
            )
            row = cur.fetchone()
            if not row:
                raise SystemExit(f"taxonomy version not found: {requested_version}")
            version = requested_version
        else:
            cur.execute("SELECT version FROM derived.taxonomy_node ORDER BY version DESC LIMIT 1")
            row = cur.fetchone()
            if not row:
                raise SystemExit("no taxonomy versions found")
            version = row[0]

        cur.execute(
            "SELECT code, parent_code, label, COALESCE(synonyms, '[]'::jsonb) "
            "FROM derived.taxonomy_node WHERE version = %s",
            (version,),
        )
        rows = cur.fetchall()
        nodes = {code: parent for code, parent, _label, _synonyms in rows}
        children = {}
        node_list = []
        for code, parent, label, synonyms in rows:
            if parent:
                children.setdefault(parent, set()).add(code)
            node_list.append({
                "code": code,
                "label": label,
                "synonyms": list(synonyms or []),
            })
        leaf_codes = {code for code in nodes if code not in children}

        descendants = {code: set() for code in nodes}
        for code in nodes:
            stack = [code]
            seen = set()
            while stack:
                current = stack.pop()
                for child in children.get(current, set()):
                    if child in seen:
                        continue
                    seen.add(child)
                    descendants[code].add(child)
                    stack.append(child)
    return version, node_list, leaf_codes, descendants


def _derive_parent_code(code: str, code_set: set[str]) -> str | None:
    parts = code.split(".")
    while len(parts) > 1:
        parts = parts[:-1]
        candidate = ".".join(parts)
        if candidate in code_set:
            return candidate
    return None


def _build_leaf_and_descendants(parent_map: dict[str, str | None]) -> tuple[set[str], dict[str, set[str]]]:
    children: dict[str, set[str]] = {}
    for code, parent in parent_map.items():
        if parent:
            children.setdefault(parent, set()).add(code)

    descendants = {code: set() for code in parent_map}
    for code in parent_map:
        stack = list(children.get(code, set()))
        while stack:
            child = stack.pop()
            if child in descendants[code]:
                continue
            descendants[code].add(child)
            stack.extend(children.get(child, set()))

    leaf_codes = {code for code in parent_map if code not in children}
    return leaf_codes, descendants


def _resolve_taxonomy_file(requested_version: str | None) -> Path:
    if requested_version:
        candidate = TAXONOMY_ROOT / requested_version / "taxonomy.yaml"
        if candidate.exists():
            return candidate
        raise FileNotFoundError(f"taxonomy file not found for version {requested_version}: {candidate}")

    candidates = sorted(
        path for path in TAXONOMY_ROOT.glob("*/taxonomy.yaml") if path.is_file()
    )
    if not candidates:
        raise FileNotFoundError(f"no taxonomy files found under {TAXONOMY_ROOT}")
    return candidates[-1]


def get_taxonomy_version_and_nodes_from_file(requested_version: str | None) -> tuple[str, list[dict], set[str], dict]:
    taxonomy_file = _resolve_taxonomy_file(requested_version)
    taxonomy = load_taxonomy_file(taxonomy_file)
    version = str(taxonomy.get("version") or taxonomy_file.parent.name)

    raw_nodes = taxonomy.get("nodes") or []
    node_list: list[dict] = []
    codes: set[str] = set()
    for node in raw_nodes:
        code = str(node.get("code") or "").strip()
        if not code:
            continue
        codes.add(code)

    parent_map: dict[str, str | None] = {}
    for node in raw_nodes:
        code = str(node.get("code") or "").strip()
        if not code:
            continue
        label = str(node.get("label") or code).strip()
        synonyms_value = node.get("synonyms")
        synonyms = [str(item) for item in synonyms_value] if isinstance(synonyms_value, list) else []
        parent_map[code] = _derive_parent_code(code, codes)
        node_list.append({"code": code, "label": label, "synonyms": synonyms})

    leaf_codes, descendants = _build_leaf_and_descendants(parent_map)
    return version, node_list, leaf_codes, descendants


def load_taxonomy_nodes(requested_version: str | None, dsn: str | None) -> tuple[str, list[dict], set[str], dict]:
    require_db = os.getenv("INTENT_REQUIRE_DB") == "1"
    if dsn and dsn not in _UNAVAILABLE_DSN:
        try:
            with psycopg.connect(dsn) as conn:
                return get_taxonomy_version_and_nodes(conn, requested_version)
        except psycopg.Error:
            _UNAVAILABLE_DSN.add(dsn)
            if require_db:
                raise

    return get_taxonomy_version_and_nodes_from_file(requested_version)


def detect_posture(text: str) -> str:
    for pattern, posture in POSTURE_RULES:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return posture
    return "UNKNOWN"


def build_phrase_index(nodes: list[dict]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    phrase_to_codes: dict[str, list[str]] = {}
    keyword_to_codes: dict[str, list[str]] = {}
    for node in nodes:
        code = node["code"]
        phrases = [node.get("label") or ""] + (node.get("synonyms") or [])
        for phrase in phrases:
            norm = phrase.strip().lower()
            if not norm:
                continue
            phrase_to_codes.setdefault(norm, []).append(code)
            for token in norm.split():
                keyword_to_codes.setdefault(token, []).append(code)
    return phrase_to_codes, keyword_to_codes


def score_codes(text: str, nodes: list[dict]) -> tuple[Dict[str, float], List[str]]:
    scores: Dict[str, float] = {}
    matched_doctrines: List[str] = []
    text_lower = text.lower()
    phrase_to_codes, keyword_to_codes = build_phrase_index(nodes)

    for phrase, codes in phrase_to_codes.items():
        if phrase in text_lower:
            for code in codes:
                scores[code] = min(0.95, scores.get(code, 0.0) + 0.5)

    for pattern, keyword, weight, kind in RULES:
        if re.search(pattern, text, flags=re.IGNORECASE):
            matched_codes = set()
            for key, codes in phrase_to_codes.items():
                if keyword in key:
                    matched_codes.update(codes)
            if not matched_codes:
                for code in keyword_to_codes.get(keyword, []):
                    matched_codes.add(code)
            for code in matched_codes:
                scores[code] = min(0.95, scores.get(code, 0.0) + weight)
            if kind == "doctrine" and matched_codes:
                matched_doctrines.append(keyword)
    return scores, matched_doctrines


def choose_leaf(code: str, leaf_codes: set[str], descendants: dict) -> str | None:
    if code in leaf_codes:
        return code
    leaf_desc = sorted([c for c in descendants.get(code, set()) if c in leaf_codes])
    return leaf_desc[0] if leaf_desc else None


def choose_default_leaf(codes: list[str]) -> str:
    for suffix in (".GEN.GEN", ".GEN"):
        for code in codes:
            if code.endswith(suffix):
                return code
    return codes[0]


def enforce_leaf_codes(scores: Dict[str, float], leaf_codes: set[str], descendants: dict) -> Dict[str, float]:
    filtered: Dict[str, float] = {}
    for code, score in scores.items():
        leaf = choose_leaf(code, leaf_codes, descendants)
        if not leaf:
            continue
        filtered[leaf] = max(filtered.get(leaf, 0.0), score)
    return filtered


def choose_primary_secondary(scores: Dict[str, float], leaf_codes: set[str], matched_doctrines: List[str]) -> tuple[dict, list]:
    if not scores:
        default_code = sorted(leaf_codes)[0] if leaf_codes else "UNKNOWN"
        return ({"code": default_code, "confidence": 0.1}, [])

    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    primary_code, primary_score = ordered[0]
    secondary = [
        {"code": code, "confidence": round(score, 3)}
        for code, score in ordered[1:7]
    ]

    if len(set(matched_doctrines)) > 1:
        primary_score = max(0.1, primary_score - 0.15)

    return {"code": primary_code, "confidence": round(primary_score, 3)}, secondary


def classify(text: str, version_override: str | None = None, dsn_override: str | None = None) -> dict:
    dsn = dsn_override or os.getenv("COURTLISTENER_DB_DSN") or os.getenv("INTENT_DB_DSN") or DEFAULT_DSN
    version, nodes, leaf_codes, descendants = load_taxonomy_nodes(version_override, dsn)

    posture = detect_posture(text)
    scores, matched_doctrines = score_codes(text, nodes)

    suppression_triggered = any(re.search(p, text, flags=re.IGNORECASE) for p in SUPPRESSION_PATTERNS)
    scores = enforce_leaf_codes(scores, leaf_codes, descendants)

    if suppression_triggered:
        suppression_candidates = [
            code for code in sorted(leaf_codes)
            if code.startswith("4A.SUPP")
        ]
        if not suppression_candidates:
            suppression_candidates = [
                code for code in sorted(leaf_codes)
                if code.startswith("4A.SEIZ") or code.startswith("4A.WARR") or code.startswith("4A.EXC")
            ]
        if suppression_candidates:
            primary_code = choose_default_leaf(suppression_candidates)
            primary_score = max(scores.get(primary_code, 0.0), 0.8)
            secondary = [
                {"code": code, "confidence": round(score, 3)}
                for code, score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))
                if code != primary_code
            ][:6]
            if len(set(matched_doctrines)) > 1:
                primary_score = max(0.1, primary_score - 0.15)
            primary = {"code": primary_code, "confidence": round(primary_score, 3)}
        else:
            primary, secondary = choose_primary_secondary(scores, leaf_codes, matched_doctrines)
    else:
        primary, secondary = choose_primary_secondary(scores, leaf_codes, matched_doctrines)

    return {
        "primary": {**primary, "version": version},
        "secondary": [{**item, "version": version} for item in secondary],
        "posture": posture,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Rules-only intent service v1")
    parser.add_argument("--text", required=True, help="Raw user input text")
    parser.add_argument("--version", default=None, help="Taxonomy version override")
    args = parser.parse_args()

    output = classify(args.text, args.version)
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
