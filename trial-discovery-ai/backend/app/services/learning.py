from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.chunk import Chunk
from app.db.models.document import Document
from app.db.models.enums import PassStatus
from app.db.models.pass_run import PassRun
from app.db.models.user_action import UserAction
from app.core.llm.schemas import Pass4Schema


@dataclass(frozen=True)
class RescoreResult:
    rescored: int


def rescore_priorities(*, session: Session, matter_id: str, user_id: str) -> RescoreResult:
    hot_doc_ids = _get_hot_doc_ids(session, matter_id, user_id)
    if not hot_doc_ids:
        return RescoreResult(rescored=0)

    centroid = _compute_centroid(session, hot_doc_ids)
    if centroid is None:
        return RescoreResult(rescored=0)

    documents = session.execute(
        select(Document).where(
            Document.matter_id == matter_id,
            Document.uploaded_by_user_id == user_id,
        )
    ).scalars().all()

    rescored = 0
    for document in documents:
        if str(document.id) in hot_doc_ids:
            continue
        similarity = _cosine_similarity(
            centroid,
            _document_embedding(session, document.id),
        )
        if similarity is None:
            continue

        priority_code = _priority_from_similarity(similarity)
        rationale = [
            "Similar to hot docs you marked",
            f"Similarity score {similarity:.2f}",
        ]

        pass4 = Pass4Schema(
            priority_code=priority_code,
            priority_rationale=rationale,
            hot_doc_candidate=False,
            hot_doc_confidence=None,
            exhibit_candidate={"is_candidate": False, "purposes": []},
            similarity_hooks=["hot-doc-centroid"],
            evidence=[],
        )

        _insert_pass4_override(session, document.id, pass4)
        rescored += 1

    return RescoreResult(rescored=rescored)


def _get_hot_doc_ids(session: Session, matter_id: str, user_id: str) -> set[str]:
    actions = session.execute(
        select(UserAction).where(
            UserAction.matter_id == matter_id,
            UserAction.user_id == user_id,
            UserAction.action_type.in_(["MARK_HOT"]),
        )
    ).scalars().all()
    return {str(action.document_id) for action in actions}


def _compute_centroid(session: Session, doc_ids: set[str]) -> list[float] | None:
    vectors = []
    for doc_id in doc_ids:
        vector = _document_embedding(session, doc_id)
        if vector is not None:
            vectors.append(vector)

    if not vectors:
        return None

    dim = len(vectors[0])
    centroid = [0.0] * dim
    for vector in vectors:
        for idx, value in enumerate(vector):
            centroid[idx] += value
    return [value / len(vectors) for value in centroid]


def _document_embedding(session: Session, document_id: str) -> list[float] | None:
    chunk = session.execute(
        select(Chunk).where(
            Chunk.document_id == document_id,
            Chunk.chunk_index == -1,
        )
    ).scalar_one_or_none()
    if not chunk:
        chunk = session.execute(
            select(Chunk).where(Chunk.document_id == document_id)
        ).scalar_one_or_none()
    if not chunk or not chunk.embedding:
        return None
    return list(chunk.embedding)


def _cosine_similarity(a: list[float] | None, b: list[float] | None) -> float | None:
    if a is None or b is None:
        return None
    if len(a) != len(b):
        return None
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return None
    return dot / (norm_a * norm_b)


def _priority_from_similarity(similarity: float) -> str:
    if similarity >= 0.85:
        return "P1"
    if similarity >= 0.7:
        return "P2"
    if similarity >= 0.5:
        return "P3"
    return "P4"


def _insert_pass4_override(session: Session, document_id: str, pass4: Pass4Schema) -> None:
    session.execute(
        PassRun.__table__.update()
        .where(PassRun.document_id == document_id, PassRun.pass_num == 4)
        .values(is_latest=False)
    )

    pass_run = PassRun(
        document_id=document_id,
        pass_num=4,
        model_id="learning_rescore",
        model_version="",
        prompt_id="learning_rescore_v1",
        prompt_hash="",
        settings_json={"method": "similarity_centroid"},
        input_artifact_hashes_json={},
        output_json=pass4.model_dump(),
        status=PassStatus.SUCCESS,
        created_at=datetime.now(timezone.utc),
        is_latest=True,
    )
    session.add(pass_run)
    session.commit()
