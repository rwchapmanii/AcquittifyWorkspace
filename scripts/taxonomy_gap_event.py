#!/usr/bin/env python3
import argparse
import json
import os
import re
from collections import Counter
from typing import Any

import psycopg

DEFAULT_DSN = "postgresql://acquittify@localhost:5432/courtlistener"


def _fallback_code(code: str) -> str:
    parts = code.split(".")
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[1]}.GEN.GEN"
    return f"{code}.GEN.GEN"


def _extract_phrases(text: str, nodes: list[dict]) -> list[str]:
    text_lower = text.lower()
    matches = []
    for node in nodes:
        phrases = [node.get("label") or ""] + (node.get("synonyms") or [])
        for phrase in phrases:
            phrase_norm = phrase.strip().lower()
            if phrase_norm and phrase_norm in text_lower:
                matches.append(phrase_norm)
    if matches:
        counts = Counter(matches)
        return [phrase for phrase, _ in counts.most_common(10)]

    tokens = re.findall(r"\b[a-z0-9\(\)\-]+\b", text_lower)
    bigrams = [" ".join(tokens[i:i+2]) for i in range(len(tokens) - 1)]
    counts = Counter(bigrams)
    return [phrase for phrase, _ in counts.most_common(10)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Record taxonomy gap events")
    parser.add_argument("--input", required=True, help="Raw user input text")
    parser.add_argument("--intent", required=True, help="Intent JSON string")
    parser.add_argument("--needs-clarification", action="store_true")
    parser.add_argument("--circuit", default=None)
    args = parser.parse_args()

    intent = json.loads(args.intent)
    primary = intent.get("primary", {})
    secondary = intent.get("secondary", [])
    posture = intent.get("posture", "UNKNOWN")

    primary_code = primary.get("code")
    primary_conf = float(primary.get("confidence", 0))
    version = primary.get("version")

    if not primary_code or not version:
        raise SystemExit("intent primary.code and primary.version are required")

    secondary_codes = [item.get("code") for item in secondary if item.get("code")]
    secondary_confidences = [float(item.get("confidence", 0)) for item in secondary if item.get("code")]

    candidates = [(primary_code, primary_conf)] + list(zip(secondary_codes, secondary_confidences))
    top_two = sorted(candidates, key=lambda x: (-x[1], x[0]))[:2]
    top_candidate_code = top_two[0][0] if top_two else None
    top_candidate_conf = top_two[0][1] if top_two else None
    second_candidate_code = top_two[1][0] if len(top_two) > 1 else None
    second_candidate_conf = top_two[1][1] if len(top_two) > 1 else None

    gap_reasons = []
    if primary_conf < 0.60:
        gap_reasons.append("LOW_CONFIDENCE")
    if primary_code.endswith(".GEN.GEN"):
        gap_reasons.append("GEN_GEN")
    if second_candidate_conf is not None and abs(top_candidate_conf - second_candidate_conf) <= 0.08:
        gap_reasons.append("CLOSE_COMPETITION")
    if args.needs_clarification:
        gap_reasons.append("CLARIFICATION")

    if not gap_reasons:
        return

    fallback_code = primary_code if primary_code.endswith(".GEN.GEN") else _fallback_code(primary_code)
    domain = primary_code.split(".")[0]

    dsn = os.getenv("COURTLISTENER_DB_DSN") or os.getenv("INTENT_DB_DSN") or DEFAULT_DSN

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT code, label, COALESCE(synonyms, '[]'::jsonb) FROM derived.taxonomy_node WHERE version = %s",
                (version,),
            )
            nodes = [
                {"code": row[0], "label": row[1], "synonyms": list(row[2] or [])}
                for row in cur.fetchall()
            ]

            phrases = _extract_phrases(args.input, nodes)

            cur.execute(
                """
                INSERT INTO derived.taxonomy_gap_event (
                    input_text,
                    intent_json,
                    taxonomy_version,
                    primary_code,
                    primary_confidence,
                    secondary_codes,
                    secondary_confidences,
                    top_candidate_code,
                    top_candidate_confidence,
                    second_candidate_code,
                    second_candidate_confidence,
                    needs_clarification,
                    gap_reasons,
                    fallback_code,
                    domain,
                    posture,
                    circuit,
                    signal_phrases
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                )
                """,
                (
                    args.input,
                    json.dumps(intent),
                    version,
                    primary_code,
                    primary_conf,
                    secondary_codes,
                    secondary_confidences,
                    top_candidate_code,
                    top_candidate_conf,
                    second_candidate_code,
                    second_candidate_conf,
                    args.needs_clarification,
                    gap_reasons,
                    fallback_code,
                    domain,
                    posture,
                    args.circuit,
                    phrases,
                ),
            )
            conn.commit()


if __name__ == "__main__":
    main()
