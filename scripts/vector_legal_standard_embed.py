#!/usr/bin/env python3
import argparse
import os
import re
from dataclasses import dataclass
from typing import Iterable, List, Optional

import chromadb
from chromadb.config import Settings
import psycopg
from sentence_transformers import SentenceTransformer

from acquittify.config import EMBEDDING_MODEL_ID
from acquittify.paths import CHROMA_DIR

DEFAULT_DSN = "postgresql://acquittify@localhost:5432/courtlistener"
DEFAULT_CHROMA_DIR = str(CHROMA_DIR)
COLLECTION_NAME = "vs_legal_standard"

TOKEN_TARGET_MIN = 250
TOKEN_TARGET_MAX = 450
TOKEN_HARD_MAX = 600
TOKEN_ABSOLUTE_MAX = 750

RULE_PATTERN = re.compile(
    r"\b(test|factors?|standard|requires|we hold|rule)\b",
    re.IGNORECASE,
)


@dataclass
class UnitRow:
    unit_id: str
    unit_text: str
    unit_type: str
    taxonomy_code: str
    taxonomy_version: str
    circuit: str
    court_level: str
    year: int
    posture: str
    standard_of_review: str
    is_holding: bool
    is_dicta: bool
    authority_weight: int
    favorability: int
    secondary_taxonomy_ids: List[str]


def _token_count(text: str) -> int:
    return len(re.findall(r"\w+|\S", text or ""))


def _split_paragraphs(text: str) -> List[str]:
    parts = re.split(r"\n\s*\n", text or "")
    return [p.strip() for p in parts if p.strip()]


def _split_sentences(text: str) -> List[str]:
    sentences = re.split(r"(?<=[\.\?\!])\s+", text.strip())
    return [s.strip() for s in sentences if s.strip()]


def _is_multifactor(text: str) -> bool:
    lower = text.lower()
    if "factor" in lower and ("first" in lower or "second" in lower or re.search(r"\(\d+\)", text)):
        return True
    return False


def _chunk_text(text: str) -> List[str]:
    paragraphs = _split_paragraphs(text)
    chunks: List[str] = []
    current: List[str] = []
    current_tokens = 0

    def flush():
        nonlocal current, current_tokens
        if current:
            chunks.append("\n\n".join(current))
            current = []
            current_tokens = 0

    for para in paragraphs:
        para_tokens = _token_count(para)
        if para_tokens > TOKEN_ABSOLUTE_MAX:
            if _is_multifactor(para) and para_tokens <= TOKEN_ABSOLUTE_MAX:
                flush()
                chunks.append(para)
                continue
            sentences = _split_sentences(para)
            buffer: List[str] = []
            buffer_tokens = 0
            for sentence in sentences:
                stokens = _token_count(sentence)
                if buffer_tokens + stokens > TOKEN_ABSOLUTE_MAX and buffer:
                    chunks.append(" ".join(buffer))
                    buffer = [sentence]
                    buffer_tokens = stokens
                else:
                    buffer.append(sentence)
                    buffer_tokens += stokens
            if buffer:
                chunks.append(" ".join(buffer))
            continue

        if current_tokens + para_tokens <= TOKEN_TARGET_MAX:
            current.append(para)
            current_tokens += para_tokens
            continue

        if current_tokens >= TOKEN_TARGET_MIN:
            flush()
            current.append(para)
            current_tokens = para_tokens
        else:
            current.append(para)
            current_tokens += para_tokens
            flush()

    flush()

    normalized: List[str] = []
    for chunk in chunks:
        tokens = _token_count(chunk)
        if tokens <= TOKEN_HARD_MAX:
            normalized.append(chunk)
        elif tokens <= TOKEN_ABSOLUTE_MAX:
            normalized.append(chunk)
        else:
            sentences = _split_sentences(chunk)
            buffer = []
            buffer_tokens = 0
            for sentence in sentences:
                stokens = _token_count(sentence)
                if buffer_tokens + stokens > TOKEN_ABSOLUTE_MAX and buffer:
                    normalized.append(" ".join(buffer))
                    buffer = [sentence]
                    buffer_tokens = stokens
                else:
                    buffer.append(sentence)
                    buffer_tokens += stokens
            if buffer:
                normalized.append(" ".join(buffer))
    return normalized


def _eligible(unit_type: str, unit_text: str) -> bool:
    if unit_type == "LEGAL_STANDARD":
        return True
    if unit_type == "HOLDING" and RULE_PATTERN.search(unit_text or ""):
        return True
    return False


def _column_exists(conn, column: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'derived'
              AND table_name = 'legal_unit'
              AND column_name = %s
            """,
            (column,),
        )
        return cur.fetchone() is not None


def _fetch_units(conn, limit: int | None) -> Iterable[UnitRow]:
    has_court_level = _column_exists(conn, "court_level")
    has_sor = _column_exists(conn, "standard_of_review")
    has_secondary = _column_exists(conn, "secondary_taxonomy_ids")
    has_authority = _column_exists(conn, "authority_weight")
    has_favorability = _column_exists(conn, "favorability")

    court_level_sql = "COALESCE(court_level, 'UNKNOWN')" if has_court_level else "'UNKNOWN'"
    sor_sql = "COALESCE(standard_of_review, 'UNKNOWN')" if has_sor else "'UNKNOWN'"
    secondary_sql = "COALESCE(secondary_taxonomy_ids, ARRAY[]::text[])" if has_secondary else "ARRAY[]::text[]"
    authority_sql = "COALESCE(authority_weight, 0)" if has_authority else "0"
    if has_favorability:
        favorability_sql = "CASE WHEN favorability::text ~ '^-?\\d+$' THEN favorability::int ELSE 0 END"
    else:
        favorability_sql = "0"

    sql = f"""
        SELECT
            unit_id,
            unit_text,
            unit_type,
            taxonomy_code,
            taxonomy_version,
            circuit,
            {court_level_sql} AS court_level,
            year,
            posture,
            {sor_sql} AS standard_of_review,
            is_holding,
            is_dicta,
            {authority_sql} AS authority_weight,
            {favorability_sql} AS favorability,
            {secondary_sql} AS secondary_taxonomy_ids
        FROM derived.legal_unit
        WHERE unit_type IN ('LEGAL_STANDARD', 'HOLDING')
        ORDER BY id
    """
    if limit:
        sql += " LIMIT %s"
        params = (limit,)
    else:
        params = ()

    with conn.cursor() as cur:
        cur.execute(sql, params)
        for row in cur.fetchall():
            unit = UnitRow(*row)
            if _eligible(unit.unit_type, unit.unit_text):
                yield unit


def _get_client(chroma_dir: str):
    try:
        return chromadb.PersistentClient(path=chroma_dir)
    except Exception:
        settings = Settings(persist_directory=chroma_dir, anonymized_telemetry=False)
        return chromadb.Client(settings)


def main() -> None:
    parser = argparse.ArgumentParser(description="Embed legal standard units into vs_legal_standard")
    parser.add_argument("--limit", type=int, default=None, help="Limit rows processed")
    parser.add_argument("--chroma-dir", default=os.getenv("CHROMA_DIR", DEFAULT_CHROMA_DIR))
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()

    dsn = os.getenv("COURTLISTENER_DB_DSN") or DEFAULT_DSN
    model = SentenceTransformer(EMBEDDING_MODEL_ID)

    client = _get_client(args.chroma_dir)
    collection = client.get_or_create_collection(name=COLLECTION_NAME)

    with psycopg.connect(dsn) as conn:
        buffer_texts: List[str] = []
        buffer_ids: List[str] = []
        buffer_meta: List[dict] = []

        for unit in _fetch_units(conn, args.limit):
            chunks = _chunk_text(unit.unit_text)
            for idx, chunk in enumerate(chunks):
                chunk_id = f"{unit.unit_id}:{idx}"
                taxonomy_prefixes = []
                if unit.taxonomy_code:
                    parts = unit.taxonomy_code.split(".")
                    for i in range(1, len(parts) + 1):
                        taxonomy_prefixes.append(".".join(parts[:i]))
                metadata = {
                    "unit_id": unit.unit_id,
                    "primary_taxonomy_id": unit.taxonomy_code,
                    "secondary_taxonomy_ids": unit.secondary_taxonomy_ids,
                    "taxonomy_prefixes": taxonomy_prefixes,
                    "taxonomy_version": unit.taxonomy_version,
                    "circuit": unit.circuit,
                    "court_level": unit.court_level,
                    "year": unit.year,
                    "posture": unit.posture,
                    "standard_of_review": unit.standard_of_review,
                    "is_holding": unit.is_holding,
                    "is_dicta": unit.is_dicta,
                    "authority_weight": unit.authority_weight,
                    "favorability": unit.favorability,
                }
                buffer_texts.append(chunk)
                buffer_ids.append(chunk_id)
                buffer_meta.append(metadata)

                if len(buffer_texts) >= args.batch_size:
                    embeddings = model.encode(buffer_texts).tolist()
                    collection.upsert(
                        ids=buffer_ids,
                        documents=buffer_texts,
                        embeddings=embeddings,
                        metadatas=buffer_meta,
                    )
                    buffer_texts, buffer_ids, buffer_meta = [], [], []

        if buffer_texts:
            embeddings = model.encode(buffer_texts).tolist()
            collection.upsert(
                ids=buffer_ids,
                documents=buffer_texts,
                embeddings=embeddings,
                metadatas=buffer_meta,
            )


if __name__ == "__main__":
    main()
