from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.chunk import Chunk
from app.db.models.document import Document
from app.services.embedding import embed_text


@dataclass(frozen=True)
class SearchHit:
    chunk_id: str
    document_id: str
    score: float
    page_num: int | None
    text: str
    source_path: str
    original_filename: str


def hybrid_search(
    *,
    session: Session,
    matter_id: str,
    user_id: UUID | str | None = None,
    query: str,
    limit: int = 20,
    vector_limit: int = 60,
    lexical_limit: int = 60,
    rrf_k: int = 60,
) -> list[SearchHit]:
    if not query.strip():
        return []

    tsquery = func.websearch_to_tsquery("english", query)
    visibility_filters = [Document.matter_id == matter_id]
    if user_id:
        visibility_filters.append(Document.uploaded_by_user_id == user_id)

    vector_rows = []
    try:
        query_vector = embed_text(query).vector
        vector_rows = session.execute(
            select(
                Chunk,
                Document,
                Chunk.embedding.cosine_distance(query_vector).label("distance"),
            )
            .join(Document, Document.id == Chunk.document_id)
            .where(
                Chunk.embedding.isnot(None),
                *visibility_filters,
            )
            .order_by("distance")
            .limit(vector_limit)
        ).all()
    except Exception:  # noqa: BLE001
        # Run lexical retrieval only when embeddings are unavailable.
        vector_rows = []

    rank_expr = func.ts_rank_cd(func.to_tsvector("english", Chunk.text), tsquery)
    lexical_rows = session.execute(
        select(
            Chunk,
            Document,
            rank_expr.label("rank"),
        )
        .join(Document, Document.id == Chunk.document_id)
        .where(
            *visibility_filters,
            func.to_tsvector("english", Chunk.text).op("@@")(tsquery),
        )
        .order_by(rank_expr.desc())
        .limit(lexical_limit)
    ).all()

    scores: dict[str, dict[str, Any]] = {}

    for rank, (chunk, doc, _distance) in enumerate(vector_rows, start=1):
        _upsert_hit(scores, chunk, doc, 1.0 / (rrf_k + rank))

    for rank, (chunk, doc, _score) in enumerate(lexical_rows, start=1):
        _upsert_hit(scores, chunk, doc, 1.0 / (rrf_k + rank))

    hits = sorted(scores.values(), key=lambda item: item["score"], reverse=True)
    return [
        SearchHit(
            chunk_id=item["chunk_id"],
            document_id=item["document_id"],
            score=item["score"],
            page_num=item["page_num"],
            text=item["text"],
            source_path=item["source_path"],
            original_filename=item["original_filename"],
        )
        for item in hits[:limit]
    ]


def _upsert_hit(scores: dict[str, dict[str, Any]], chunk: Chunk, doc: Document, score: float) -> None:
    key = str(chunk.id)
    if key not in scores:
        scores[key] = {
            "chunk_id": key,
            "document_id": str(doc.id),
            "score": 0.0,
            "page_num": chunk.page_num,
            "text": chunk.text,
            "source_path": doc.source_path,
            "original_filename": doc.original_filename,
        }
    scores[key]["score"] += score
