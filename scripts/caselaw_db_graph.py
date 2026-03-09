#!/usr/bin/env python3
"""Build a caselaw ontology graph payload from Postgres derived tables."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

import psycopg
from psycopg.rows import dict_row


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate caselaw ontology graph JSON from Postgres")
    parser.add_argument(
        "--db-dsn",
        default=os.getenv("ACQ_CASELAW_DB_DSN") or os.getenv("COURTLISTENER_DB_DSN", ""),
        help="Postgres DSN",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=int(os.getenv("ACQ_CASELAW_GRAPH_LIMIT", "20000")),
        help="Maximum cases to include",
    )
    return parser.parse_args()


def as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def case_domain(case_type: str) -> str:
    text = as_str(case_type).lower()
    if "criminal" in text:
        return "criminal"
    if "quasi" in text:
        return "criminal"
    return "civil"


def court_level_bucket(value: str) -> str:
    text = as_str(value).lower()
    if text in {"scotus", "supreme", "supreme_court"}:
        return "supreme"
    if text in {"circuit", "appeals"}:
        return "appeals"
    if text in {"district"}:
        return "district"
    if "supreme" in text:
        return "supreme"
    if "circuit" in text or "appeal" in text:
        return "appeals"
    if "district" in text:
        return "district"
    return "other"


def main() -> int:
    args = parse_args()
    dsn = as_str(args.db_dsn)
    if not dsn:
        print(json.dumps({"nodes": [], "edges": [], "meta": {"exists": False, "reason": "missing_db_dsn"}}))
        return 0

    limit = max(100, min(int(args.limit), 100000))
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    node_type_counts: dict[str, int] = {}
    edge_type_counts: dict[str, int] = {}
    case_domain_counts: dict[str, int] = {}
    circuit_counts: dict[str, int] = {}
    taxonomy_nodes: dict[str, dict[str, Any]] = {}
    taxonomy_label_map: dict[str, str] = {}

    with psycopg.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT COUNT(*) AS total FROM derived.caselaw_nightly_case")
            total_cases = int(cur.fetchone()["total"] or 0)

            cur.execute(
                """
                SELECT code, label
                FROM derived.taxonomy_node
                WHERE version = (SELECT MAX(version) FROM derived.taxonomy_node)
                """
            )
            for row in cur.fetchall():
                code = as_str(row.get("code"))
                label = as_str(row.get("label")) or code
                if code:
                    taxonomy_label_map[code] = label

            cur.execute(
                """
                SELECT
                    case_id,
                    case_name,
                    court_id,
                    court_name,
                    date_filed,
                    case_type,
                    taxonomy_codes,
                    frontmatter_json
                FROM derived.caselaw_nightly_case
                ORDER BY date_filed DESC NULLS LAST, last_ingested_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()

    for row in rows:
        case_id = as_str(row.get("case_id"))
        if not case_id:
            continue
        case_name = as_str(row.get("case_name")) or case_id
        court_id = as_str(row.get("court_id")).lower()
        date_filed = row.get("date_filed")
        date_text = date_filed.isoformat() if hasattr(date_filed, "isoformat") else as_str(date_filed)
        decision_year = date_text[:4] if len(date_text) >= 4 else ""
        frontmatter = row.get("frontmatter_json") if isinstance(row.get("frontmatter_json"), dict) else {}
        sources = frontmatter.get("sources") if isinstance(frontmatter.get("sources"), dict) else {}
        citations = frontmatter.get("citations_in_text") if isinstance(frontmatter.get("citations_in_text"), list) else []
        primary_citation = as_str(sources.get("primary_citation")) or (as_str(citations[0]) if citations else "")
        label = case_name
        if decision_year:
            label = f"{label} ({decision_year})"
        if primary_citation:
            label = f"{label}, {primary_citation}"

        court_level = court_level_bucket(as_str(frontmatter.get("court_level")) or as_str(row.get("court_name")))
        domain = case_domain(as_str(row.get("case_type")))
        summary = as_str(frontmatter.get("case_summary"))
        holding = as_str(frontmatter.get("essential_holding"))
        search_parts = [
            case_id,
            case_name,
            label,
            primary_citation,
            date_text,
            court_id,
            court_level,
            domain,
            summary,
            holding,
        ]
        search_text = " ".join(part.lower() for part in search_parts if part)

        nodes.append(
            {
                "id": case_id,
                "nodeType": "case",
                "label": label,
                "caseId": case_id,
                "caseTitle": case_name,
                "caseDisplayLabel": label,
                "caseCitation": primary_citation,
                "courtLevel": court_level,
                "court": as_str(row.get("court_name")),
                "decisionDate": date_text,
                "decisionYear": decision_year,
                "caseSummary": summary,
                "essentialHolding": holding,
                "caseDomain": domain,
                "originatingCircuit": court_id,
                "originatingCircuitLabel": court_id,
                "searchText": search_text,
            }
        )
        node_type_counts["case"] = node_type_counts.get("case", 0) + 1
        case_domain_counts[domain] = case_domain_counts.get(domain, 0) + 1
        if court_id:
            circuit_counts[court_id] = circuit_counts.get(court_id, 0) + 1

        for code_raw in row.get("taxonomy_codes") or []:
            code = as_str(code_raw)
            if not code:
                continue
            taxonomy_id = f"taxonomy.{code}"
            if taxonomy_id not in taxonomy_nodes:
                taxonomy_label = taxonomy_label_map.get(code, code)
                taxonomy_nodes[taxonomy_id] = {
                    "id": taxonomy_id,
                    "nodeType": "taxonomy",
                    "taxonomyCode": code,
                    "label": taxonomy_label,
                    "searchText": f"{code} {taxonomy_label}".lower(),
                }
            edges.append(
                {
                    "source": case_id,
                    "target": taxonomy_id,
                    "edgeType": "taxonomy_edge",
                    "relationType": "",
                    "citationType": "",
                    "confidence": 0.9,
                }
            )
            edge_type_counts["taxonomy_edge"] = edge_type_counts.get("taxonomy_edge", 0) + 1

    for node in taxonomy_nodes.values():
        nodes.append(node)
        node_type_counts["taxonomy"] = node_type_counts.get("taxonomy", 0) + 1

    payload = {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "ontologyRoot": "derived.caselaw_nightly_case",
            "exists": bool(nodes),
            "source": "postgres_caselaw",
            "checkedCandidates": 1,
            "scannedFiles": len(rows),
            "truncated": total_cases > len(rows),
            "nodeTypeCounts": node_type_counts,
            "edgeTypeCounts": edge_type_counts,
            "relationTypes": [],
            "citationTypes": [],
            "caseDomainCounts": case_domain_counts,
            "originatingCircuitCounts": circuit_counts,
            "fallbackFromVault": False,
            "dbFallback": True,
            "documents": len(rows),
            "totalCases": total_cases,
        },
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
