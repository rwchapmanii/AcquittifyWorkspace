#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path

import chromadb
from chromadb.config import Settings
import psycopg
from psycopg.rows import dict_row
from sentence_transformers import SentenceTransformer

from acquittify.config import EMBEDDING_MODEL_ID
from acquittify.paths import CHROMA_DIR

try:
    from scripts.retrieval_sql import SQL_QUERY
except ModuleNotFoundError:
    import sys
    from pathlib import Path as _Path

    sys.path.append(str(_Path(__file__).resolve().parents[1]))
    from scripts.retrieval_sql import SQL_QUERY

DEFAULT_DSN = "postgresql://acquittify@localhost:5432/courtlistener"
DEFAULT_CHROMA_DIR = str(CHROMA_DIR)
COLLECTION_NAME = "vs_legal_standard"
AUDIT_LOG = Path("Casefiles/vector_audit.jsonl")


def _get_client(chroma_dir: str):
    try:
        return chromadb.PersistentClient(path=chroma_dir)
    except Exception:
        settings = Settings(persist_directory=chroma_dir, anonymized_telemetry=False)
        return chromadb.Client(settings)


def _sql_retrieve(conn, intent: dict, limit: int):
    primary = intent.get("primary", {})
    secondary = intent.get("secondary", [])
    posture = intent.get("posture", "UNKNOWN")

    primary_prefix = primary.get("code")
    if not primary_prefix:
        raise SystemExit("intent.primary.code is required")

    secondary_prefixes = [item.get("code") for item in secondary if item.get("code")]
    params = (
        primary_prefix,
        secondary_prefixes,
        posture,
        limit,
    )
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(SQL_QUERY, params)
        return cur.fetchall()


def _vector_retrieve(intent: dict, query_text: str, chroma_dir: str, limit: int, circuit: str | None):
    model = SentenceTransformer(EMBEDDING_MODEL_ID)
    client = _get_client(chroma_dir)
    collection = client.get_or_create_collection(name=COLLECTION_NAME)

    primary_prefix = intent["primary"]["code"]
    secondary = intent.get("secondary", [])
    secondary_prefixes = [item.get("code") for item in secondary if item.get("code")]
    posture = intent.get("posture", "UNKNOWN")

    prefixes = [primary_prefix] + secondary_prefixes
    where = {
        "taxonomy_version": intent["primary"]["version"],
        "taxonomy_prefixes": {"$contains": primary_prefix},
    }
    if posture != "UNKNOWN":
        where["posture"] = posture

    if secondary_prefixes:
        where = {
            "$and": [
                {"taxonomy_version": intent["primary"]["version"]},
                {
                    "$or": [
                        {"taxonomy_prefixes": {"$contains": primary_prefix}},
                        *[{"taxonomy_prefixes": {"$contains": p}} for p in secondary_prefixes],
                    ]
                },
            ]
        }

    def run_query(circuit_filter: str | None, k: int):
        where_clause = dict(where)
        if circuit_filter:
            if "$and" in where_clause:
                where_clause["$and"].append({"circuit": circuit_filter})
            else:
                where_clause["circuit"] = circuit_filter
        query_embedding = model.encode([query_text]).tolist()[0]
        return collection.query(
            query_embeddings=[query_embedding],
            n_results=k,
            where=where_clause,
        )

    results = []
    if circuit:
        query_res = run_query(circuit, limit)
        results = _flatten_results(query_res, prefixes)
        if len(results) < max(5, limit // 2):
            query_res = run_query(None, limit)
            results = _flatten_results(query_res, prefixes)
    else:
        query_res = run_query(None, limit)
        results = _flatten_results(query_res, prefixes)

    return results[:limit]


def _flatten_results(query_res, prefixes):
    results = []
    for docs, metas, ids, dists in zip(
        query_res.get("documents", []),
        query_res.get("metadatas", []),
        query_res.get("ids", []),
        query_res.get("distances", []),
    ):
        for doc, meta, _id, dist in zip(docs, metas, ids, dists):
            code = meta.get("primary_taxonomy_id") if isinstance(meta, dict) else None
            if code and not any(code.startswith(prefix) for prefix in prefixes):
                continue
            results.append({
                "unit_id": meta.get("unit_id"),
                "unit_type": meta.get("unit_type", "LEGAL_STANDARD"),
                "primary_taxonomy_code": code,
                "circuit": meta.get("circuit"),
                "year": meta.get("year"),
                "posture": meta.get("posture"),
                "is_holding": meta.get("is_holding"),
                "is_dicta": meta.get("is_dicta"),
                "authority_weight": meta.get("authority_weight", 0),
                "favorability": meta.get("favorability", 0),
                "excerpt": (doc or "")[:280],
                "vector_distance": dist,
                "source": "VECTOR",
            })
    return results


def _merge_results(sql_rows, vector_rows):
    merged = {}
    for row in sql_rows:
        row["source"] = "SQL"
        merged[row["unit_id"]] = row
    for row in vector_rows:
        if row["unit_id"] in merged:
            merged[row["unit_id"]]["vector_distance"] = row.get("vector_distance")
        else:
            merged[row["unit_id"]] = row
    return list(merged.values())


def _match_depth(code: str, primary: str, secondary: list[str]) -> int:
    if code and code.startswith(primary):
        return 2
    for prefix in secondary:
        if code and code.startswith(prefix):
            return 1
    return 0


def _rank_key(row, primary, secondary):
    return (
        _match_depth(row.get("primary_taxonomy_code"), primary, secondary),
        int(row.get("authority_weight") or 0),
        1 if row.get("is_holding") else 0,
        -1 if row.get("is_dicta") else 0,
        int(row.get("favorability") or 0),
        int(row.get("year") or 0),
        -float(row.get("vector_distance") or 0),
    )


def _log_audit(data: dict):
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(data) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Hybrid SQL + vector retrieval")
    parser.add_argument("--intent", required=True, help="Intent JSON string")
    parser.add_argument("--query", required=True, help="User query text")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--vectors", action="store_true")
    parser.add_argument("--circuit", default=None)
    parser.add_argument("--chroma-dir", default=os.getenv("CHROMA_DIR", DEFAULT_CHROMA_DIR))
    args = parser.parse_args()

    intent = json.loads(args.intent)
    dsn = os.getenv("COURTLISTENER_DB_DSN") or DEFAULT_DSN

    with psycopg.connect(dsn) as conn:
        sql_rows = _sql_retrieve(conn, intent, args.limit)

    vector_attempted = False
    vector_rows = []
    if args.vectors:
        try:
            vector_attempted = True
            vector_rows = _vector_retrieve(intent, args.query, args.chroma_dir, args.limit, args.circuit)
        except Exception:
            vector_rows = []

    merged = _merge_results(sql_rows, vector_rows)

    primary_prefix = intent.get("primary", {}).get("code")
    secondary_prefixes = [item.get("code") for item in intent.get("secondary", []) if item.get("code")]

    merged.sort(key=lambda row: _rank_key(row, primary_prefix, secondary_prefixes), reverse=True)

    fallback = vector_attempted and not vector_rows
    _log_audit({
        "vector_attempted": vector_attempted,
        "vector_results_count": len(vector_rows),
        "fallback_to_sql_only": fallback,
    })

    if not merged:
        result = {"intent": intent, "results": [], "status": "EMPTY"}
    else:
        result = {"intent": intent, "results": merged, "status": "OK"}

    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
