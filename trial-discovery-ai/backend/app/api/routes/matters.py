from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, text
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth import AuthContext, get_auth_context
from app.api.authz import (
    require_admin_access,
    require_write_access,
    resolve_matter_for_org,
)
from app.api.deps import get_db
from app.db.models.document import Document
from app.db.models.enums import DocumentStatus
from app.db.models.matter import Matter
from app.workers.tasks import pass1_task
from app.services.dropbox_case_sync import sync_case_folders

router = APIRouter(prefix="/matters", tags=["matters"])


class MatterCreateRequest(BaseModel):
    name: str
    dropbox_root_path: str | None = None
    external_id: str | None = None


class ReviewDocumentsRequest(BaseModel):
    # Legacy field kept for backward compatibility with older clients.
    # Bootstrap now always queues a single processing pass.
    passes: list[int] | None = None


class DropboxSyncRequest(BaseModel):
    root_path: str | None = None


def _normalize_document_row(row: dict[str, object]) -> dict[str, object]:
    normalized = dict(row)
    raw_document_id = normalized.get("document_id") or normalized.get("id")
    if raw_document_id is not None:
        document_id = str(raw_document_id)
        normalized["document_id"] = document_id
        normalized["id"] = document_id
    return normalized


def _resolve_matter(
    *, session: Session, matter_id: str, auth: AuthContext
) -> Matter | None:
    return resolve_matter_for_org(
        session=session, matter_id=matter_id, organization_id=auth.organization.id
    )


@router.post("")
def create_matter(
    payload: MatterCreateRequest,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_write_access),
) -> dict:
    if payload.external_id:
        existing = (
            session.query(Matter)
            .filter(
                Matter.external_id == payload.external_id,
                Matter.organization_id == auth.organization.id,
            )
            .first()
        )
        if existing:
            return {
                "id": str(existing.id),
                "name": existing.name,
                "external_id": existing.external_id,
            }

    matter = Matter(
        organization_id=auth.organization.id,
        name=payload.name,
        dropbox_root_path=payload.dropbox_root_path,
        external_id=payload.external_id,
        created_by=str(auth.user.id),
    )
    session.add(matter)
    session.commit()
    session.refresh(matter)
    return {
        "id": str(matter.id),
        "name": matter.name,
        "external_id": matter.external_id,
    }


@router.get("")
def list_matters(
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> dict:
    matters = (
        session.query(Matter)
        .filter(Matter.organization_id == auth.organization.id)
        .order_by(Matter.created_at.desc())
        .all()
    )
    return {
        "matters": [
            {
                "id": str(matter.id),
                "name": matter.name,
                "external_id": matter.external_id,
                "created_at": matter.created_at.isoformat(),
            }
            for matter in matters
        ]
    }


@router.post("/sync/dropbox")
def sync_dropbox_cases(
    payload: DropboxSyncRequest,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_admin_access),
) -> dict:
    result = sync_case_folders(
        session=session,
        root_path=payload.root_path,
        organization_id=auth.organization.id,
        created_by=str(auth.user.id),
    )
    return {
        "created": [case.name for case in result.created],
        "existing": [case.name for case in result.existing],
        "total": len(result.created) + len(result.existing),
    }


@router.get("/{matter_id}")
def get_matter(
    matter_id: str,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> dict:
    matter = _resolve_matter(session=session, matter_id=matter_id, auth=auth)
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found")
    return {
        "id": str(matter.id),
        "name": matter.name,
        "external_id": matter.external_id,
        "created_at": matter.created_at.isoformat(),
    }


@router.get("/{matter_id}/documents/status")
def get_matter_document_status(
    matter_id: str,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> dict:
    matter = _resolve_matter(session=session, matter_id=matter_id, auth=auth)
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found")

    rows = (
        session.query(Document.status, func.count(Document.id))
        .filter(
            Document.matter_id == matter.id,
            Document.uploaded_by_user_id == auth.user.id,
        )
        .group_by(Document.status)
        .all()
    )
    counts = {status.value: 0 for status in DocumentStatus}
    for status, count in rows:
        counts[status.value] = count

    total = sum(counts.values())
    return {"matter_id": str(matter.id), "total": total, "counts": counts}


@router.get("/{matter_id}/documents/metadata")
def get_matter_document_metadata(
    matter_id: str,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
    limit: int = 100,
) -> dict:
    matter = _resolve_matter(session=session, matter_id=matter_id, auth=auth)
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found")

    rows = session.execute(
        text(
            """
            SELECT *
            FROM derived.document_ingestion_metadata
            WHERE matter_id = :matter_id
              AND uploaded_by_user_id = :user_id
            ORDER BY ingested_at DESC NULLS LAST
            LIMIT :limit
            """
        ),
        {"matter_id": str(matter.id), "user_id": str(auth.user.id), "limit": limit},
    ).mappings().all()

    return {
        "matter_id": str(matter.id),
        "documents": [_normalize_document_row(dict(row)) for row in rows],
    }


@router.get("/{matter_id}/documents")
def list_matter_documents(
    matter_id: str,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
    limit: int = 100,
    offset: int = 0,
    status: str | None = None,
    q: str | None = None,
    doc_type: str | None = None,
    priority_code: str | None = None,
    witness: str | None = None,
    proponent: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    matter = _resolve_matter(session=session, matter_id=matter_id, auth=auth)
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found")

    if limit <= 0 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 500")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be >= 0")

    if status:
        allowed_statuses = {status.value for status in DocumentStatus}
        if status not in allowed_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status '{status}'. Allowed: {sorted(allowed_statuses)}",
            )

    conditions: list[str] = [
        "matter_id = :matter_id",
        "uploaded_by_user_id = :user_id",
    ]
    params: dict[str, object] = {
        "matter_id": str(matter.id),
        "user_id": str(auth.user.id),
        "limit": limit,
        "offset": offset,
    }

    if status:
        conditions.append("status = :status")
        params["status"] = status

    if q:
        conditions.append(
            """
            (
                original_filename ILIKE :q
                OR COALESCE(
                    pass1_metadata->>'document_type',
                    pass1_metadata->'doc_type'->>'category',
                    ''
                ) ILIKE :q
                OR COALESCE(
                    pass1_metadata->>'proponent',
                    pass1_metadata->'authorship_transmission'->>'sender',
                    ''
                ) ILIKE :q
            )
            """
        )
        params["q"] = f"%{q}%"

    if doc_type:
        conditions.append(
            """
            COALESCE(
                pass1_metadata->>'document_type',
                pass1_metadata->'doc_type'->>'category'
            ) ILIKE :doc_type
            """
        )
        params["doc_type"] = doc_type

    if priority_code:
        conditions.append("pass4_metadata->>'priority_code' = :priority_code")
        params["priority_code"] = priority_code

    if witness:
        conditions.append("pass1_metadata->'witnesses' ? :witness")
        params["witness"] = witness

    if proponent:
        conditions.append("pass1_metadata->>'proponent' ILIKE :proponent")
        params["proponent"] = f"%{proponent}%"

    if date_from or date_to:
        date_source = (
            "COALESCE(pass1_metadata->>'document_date', "
            "pass1_metadata->'time'->>'sent_at')"
        )
        date_expr = (
            f"CASE WHEN {date_source} ~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}$' "
            f"THEN ({date_source})::date ELSE NULL END"
        )
        if date_from:
            conditions.append(f"{date_expr} >= :date_from")
            params["date_from"] = date_from
        if date_to:
            conditions.append(f"{date_expr} <= :date_to")
            params["date_to"] = date_to

    where_clause = " AND ".join(conditions)

    rows = session.execute(
        text(
            f"""
            SELECT *
            FROM derived.document_ingestion_metadata
            WHERE {where_clause}
            ORDER BY ingested_at DESC NULLS LAST
            LIMIT :limit
            OFFSET :offset
            """
        ),
        params,
    ).mappings().all()

    total = session.execute(
        text(
            f"""
            SELECT COUNT(*) AS total
            FROM derived.document_ingestion_metadata
            WHERE {where_clause}
            """
        ),
        params,
    ).scalar_one()

    return {
        "matter_id": str(matter.id),
        "total": total,
        "limit": limit,
        "offset": offset,
        "documents": [_normalize_document_row(dict(row)) for row in rows],
    }


@router.post("/{matter_id}/documents/review")
def review_matter_documents(
    matter_id: str,
    payload: ReviewDocumentsRequest | None = None,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_write_access),
) -> dict:
    matter = _resolve_matter(session=session, matter_id=matter_id, auth=auth)
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found")

    total = (
        session.query(Document.id)
        .filter(
            Document.matter_id == matter.id,
            Document.uploaded_by_user_id == auth.user.id,
        )
        .count()
    )

    eligible_statuses = [
        DocumentStatus.PREPROCESSED,
        DocumentStatus.INDEXED,
        DocumentStatus.READY,
    ]
    eligible_docs = (
        session.query(Document.id)
        .filter(
            Document.matter_id == matter.id,
            Document.uploaded_by_user_id == auth.user.id,
            Document.status.in_(eligible_statuses),
        )
        .all()
    )

    for (doc_id,) in eligible_docs:
        pass1_task.delay(str(doc_id))

    return {
        "matter_id": str(matter.id),
        "total": total,
        "passes": [1],
        "enqueued": len(eligible_docs),
        "enqueued_tasks": len(eligible_docs),
        "skipped": total - len(eligible_docs),
        "eligible_statuses": [status.value for status in eligible_statuses],
    }


@router.get("/{matter_id}/identity-feedback", response_model=None)
def export_identity_feedback(
    matter_id: str,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
    format: str = "json",
    limit: int = 500,
    offset: int = 0,
) -> Response | dict:
    matter = _resolve_matter(session=session, matter_id=matter_id, auth=auth)
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found")

    if limit <= 0 or limit > 2000:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 2000")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be >= 0")

    rows = session.execute(
        text(
            """
            SELECT
                f.id,
                f.document_id,
                d.original_filename,
                f.old_identity,
                f.new_identity,
                f.source,
                f.created_at
            FROM derived.document_identity_feedback f
            JOIN documents d ON d.id = f.document_id
            WHERE f.matter_id = :matter_id
              AND d.uploaded_by_user_id = :user_id
            ORDER BY f.created_at DESC
            LIMIT :limit
            OFFSET :offset
            """
        ),
        {
            "matter_id": str(matter.id),
            "user_id": str(auth.user.id),
            "limit": limit,
            "offset": offset,
        },
    ).mappings().all()

    if format.lower() == "csv":
        import csv
        import io

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "id",
                "document_id",
                "original_filename",
                "old_identity",
                "new_identity",
                "source",
                "created_at",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row["id"],
                    row["document_id"],
                    row["original_filename"],
                    row["old_identity"],
                    row["new_identity"],
                    row["source"],
                    row["created_at"],
                ]
            )
        return Response(content=output.getvalue(), media_type="text/csv")

    total = session.execute(
        text(
            """
            SELECT COUNT(*) AS total
            FROM derived.document_identity_feedback f
            JOIN documents d ON d.id = f.document_id
            WHERE f.matter_id = :matter_id
              AND d.uploaded_by_user_id = :user_id
            """
        ),
        {"matter_id": str(matter.id), "user_id": str(auth.user.id)},
    ).scalar_one()

    return {
        "matter_id": str(matter.id),
        "total": total,
        "limit": limit,
        "offset": offset,
        "rows": [dict(row) for row in rows],
    }
