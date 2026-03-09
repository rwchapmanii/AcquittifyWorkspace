from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.api.auth import AuthContext, get_auth_context
from app.api.authz import require_write_access, resolve_document_for_org
from app.api.deps import get_db
from app.db.models.artifact import Artifact
from app.db.models.enums import ArtifactKind, UserActionType
from app.db.models.user_action import UserAction
from app.storage.s3 import S3Client

router = APIRouter(prefix="/documents", tags=["documents"])


class MetadataOverrideRequest(BaseModel):
    pass1_metadata: dict | None = None
    pass2_metadata: dict | None = None
    pass4_metadata: dict | None = None


class DocumentActionRequest(BaseModel):
    action_type: UserActionType
    payload: dict | None = None
    user_id: str | None = None


def _identity_subset(payload: dict | None) -> dict | None:
    if not isinstance(payload, dict):
        return None
    subset_keys = {
        "doc_identity",
        "document_type",
        "document_date",
        "proponent",
        "witnesses",
        "authorship_transmission",
        "time",
        "identity_confidence",
        "identity_evidence",
    }
    return {key: payload.get(key) for key in subset_keys if key in payload}


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("s3://"):
        raise HTTPException(status_code=400, detail="Invalid artifact URI")
    path = uri.replace("s3://", "", 1)
    if "/" not in path:
        raise HTTPException(status_code=400, detail="Invalid artifact URI")
    bucket, key = path.split("/", 1)
    if not bucket or not key:
        raise HTTPException(status_code=400, detail="Invalid artifact URI")
    return bucket, key


def _apply_pass4_action(
    pass4: dict,
    action_type: UserActionType,
    payload: dict | None,
) -> dict:
    updated = dict(pass4)
    payload = payload or {}

    if action_type == UserActionType.MARK_HOT:
        updated["hot_doc_candidate"] = True
        return updated
    if action_type == UserActionType.UNMARK_HOT:
        updated["hot_doc_candidate"] = False
        return updated
    if action_type == UserActionType.MARK_EXHIBIT:
        exhibit = dict(updated.get("exhibit_candidate") or {})
        exhibit["is_candidate"] = True
        updated["exhibit_candidate"] = exhibit
        return updated
    if action_type == UserActionType.UNMARK_EXHIBIT:
        exhibit = dict(updated.get("exhibit_candidate") or {})
        exhibit["is_candidate"] = False
        updated["exhibit_candidate"] = exhibit
        return updated
    if action_type == UserActionType.PRIORITY_OVERRIDE:
        updated["priority_code"] = payload.get("priority_code")
        return updated
    if action_type == UserActionType.EVIDENCE_ADD:
        evidence = updated.get("evidence")
        if not isinstance(evidence, list):
            evidence = []
        evidence.append(
            {
                "chunk_id": payload.get("chunk_id"),
                "quote": payload.get("quote"),
                "page_num": payload.get("page_num"),
            }
        )
        updated["evidence"] = evidence
        return updated
    if action_type == UserActionType.EVIDENCE_REMOVE:
        evidence = updated.get("evidence")
        if not isinstance(evidence, list):
            return updated
        index = payload.get("index")
        if isinstance(index, int) and 0 <= index < len(evidence):
            evidence.pop(index)
        else:
            quote = payload.get("quote")
            if isinstance(quote, str):
                for idx, item in enumerate(evidence):
                    if isinstance(item, dict) and item.get("quote") == quote:
                        evidence.pop(idx)
                        break
        updated["evidence"] = evidence
        return updated

    return updated


@router.get("/{document_id}")
def get_document_detail(
    document_id: str,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> dict:
    document = resolve_document_for_org(
        session=session,
        document_id=document_id,
        organization_id=auth.organization.id,
        user_id=auth.user.id,
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    row = session.execute(
        text(
            """
            SELECT *
            FROM derived.document_ingestion_metadata
            WHERE document_id = :document_id
            """
        ),
        {"document_id": str(document.id)},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    return dict(row)


@router.get("/{document_id}/text")
def get_document_text(
    document_id: str,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> dict:
    document = resolve_document_for_org(
        session=session,
        document_id=document_id,
        organization_id=auth.organization.id,
        user_id=auth.user.id,
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    artifact = (
        session.query(Artifact)
        .filter(
            Artifact.document_id == document_id,
            Artifact.kind == ArtifactKind.EXTRACTED_TEXT,
        )
        .first()
    )
    if not artifact:
        raise HTTPException(status_code=404, detail="Extracted text not found")

    s3 = S3Client()
    bucket, key = _parse_s3_uri(artifact.uri)
    data = s3.get_bytes(bucket=bucket, key=key).decode("utf-8")

    return {"document_id": document_id, "text": data}


@router.get("/{document_id}/download-url")
def get_document_download_url(
    document_id: str,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> dict:
    document = resolve_document_for_org(
        session=session,
        document_id=document_id,
        organization_id=auth.organization.id,
        user_id=auth.user.id,
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    bucket, key = _parse_s3_uri(document.source_path)
    s3 = S3Client()
    download_url = s3.create_presigned_get_url(
        bucket=bucket,
        key=key,
        expires_in_seconds=300,
    )
    return {
        "document_id": str(document.id),
        "key": key,
        "expires_in_seconds": 300,
        "download_url": download_url,
    }


@router.post("/{document_id}/metadata")
def update_document_metadata(
    document_id: str,
    payload: MetadataOverrideRequest,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_write_access),
) -> dict:
    document = resolve_document_for_org(
        session=session,
        document_id=document_id,
        organization_id=auth.organization.id,
        user_id=auth.user.id,
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    fields_set = payload.model_fields_set
    existing_overrides = session.execute(
        text(
            """
            SELECT pass1_override, pass2_override, pass4_override
            FROM derived.document_metadata_overrides
            WHERE document_id = :document_id
            """
        ),
        {"document_id": str(document.id)},
    ).mappings().first()

    pass1_override = (
        payload.pass1_metadata
        if "pass1_metadata" in fields_set
        else existing_overrides["pass1_override"] if existing_overrides else None
    )
    pass2_override = (
        payload.pass2_metadata
        if "pass2_metadata" in fields_set
        else existing_overrides["pass2_override"] if existing_overrides else None
    )
    pass4_override = (
        payload.pass4_metadata
        if "pass4_metadata" in fields_set
        else existing_overrides["pass4_override"] if existing_overrides else None
    )

    prior_row = session.execute(
        text(
            """
            SELECT pass1_metadata
            FROM derived.document_ingestion_metadata
            WHERE document_id = :document_id
            """
        ),
        {"document_id": str(document.id)},
    ).mappings().first()

    session.execute(
        text(
            """
            INSERT INTO derived.document_metadata_overrides
                (document_id, pass1_override, pass2_override, pass4_override)
            VALUES
                (:document_id, :pass1_override, :pass2_override, :pass4_override)
            ON CONFLICT (document_id)
            DO UPDATE SET
                pass1_override = EXCLUDED.pass1_override,
                pass2_override = EXCLUDED.pass2_override,
                pass4_override = EXCLUDED.pass4_override,
                updated_at = now()
            """
        ),
        {
            "document_id": str(document.id),
            "pass1_override": pass1_override,
            "pass2_override": pass2_override,
            "pass4_override": pass4_override,
        },
    )

    if "pass1_metadata" in fields_set and payload.pass1_metadata is not None:
        old_identity = _identity_subset(prior_row["pass1_metadata"] if prior_row else None)
        new_identity = _identity_subset(payload.pass1_metadata)
        if old_identity != new_identity:
            session.execute(
                text(
                    """
                    INSERT INTO derived.document_identity_feedback
                        (document_id, matter_id, old_identity, new_identity, source)
                    VALUES
                        (:document_id, :matter_id, :old_identity, :new_identity, :source)
                    """
                ),
                {
                    "document_id": str(document.id),
                    "matter_id": str(document.matter_id),
                    "old_identity": old_identity,
                    "new_identity": new_identity,
                    "source": "override",
                },
            )
    session.commit()
    return {"document_id": str(document.id), "status": "updated"}


@router.post("/{document_id}/actions")
def create_document_action(
    document_id: str,
    payload: DocumentActionRequest,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_write_access),
) -> dict:
    document = resolve_document_for_org(
        session=session,
        document_id=document_id,
        organization_id=auth.organization.id,
        user_id=auth.user.id,
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    row = session.execute(
        text(
            """
            SELECT pass4_metadata
            FROM derived.document_ingestion_metadata
            WHERE document_id = :document_id
            """
        ),
        {"document_id": str(document.id)},
    ).mappings().first()

    pass4_current = row["pass4_metadata"] if row else {}
    if not isinstance(pass4_current, dict):
        pass4_current = {}

    updated_pass4 = pass4_current
    if payload.action_type in {
        UserActionType.MARK_HOT,
        UserActionType.UNMARK_HOT,
        UserActionType.MARK_EXHIBIT,
        UserActionType.UNMARK_EXHIBIT,
        UserActionType.PRIORITY_OVERRIDE,
        UserActionType.EVIDENCE_ADD,
        UserActionType.EVIDENCE_REMOVE,
    }:
        updated_pass4 = _apply_pass4_action(
            pass4_current, payload.action_type, payload.payload
        )

        existing_overrides = session.execute(
            text(
                """
                SELECT pass1_override, pass2_override
                FROM derived.document_metadata_overrides
                WHERE document_id = :document_id
                """
            ),
            {"document_id": str(document.id)},
        ).mappings().first()

        session.execute(
            text(
                """
                INSERT INTO derived.document_metadata_overrides
                    (document_id, pass1_override, pass2_override, pass4_override)
                VALUES
                    (:document_id, :pass1_override, :pass2_override, :pass4_override)
                ON CONFLICT (document_id)
                DO UPDATE SET
                    pass1_override = EXCLUDED.pass1_override,
                    pass2_override = EXCLUDED.pass2_override,
                    pass4_override = EXCLUDED.pass4_override,
                    updated_at = now()
                """
            ),
            {
                "document_id": str(document.id),
                "pass1_override": existing_overrides["pass1_override"]
                if existing_overrides
                else None,
                "pass2_override": existing_overrides["pass2_override"]
                if existing_overrides
                else None,
                "pass4_override": updated_pass4,
            },
        )

    action = UserAction(
        matter_id=document.matter_id,
        document_id=document.id,
        user_id=payload.user_id or str(auth.user.id),
        action_type=payload.action_type,
        payload_json=payload.payload,
    )
    session.add(action)
    session.commit()
    session.refresh(action)

    return {
        "document_id": str(document.id),
        "action_id": str(action.id),
        "action_type": action.action_type,
        "pass4_metadata": updated_pass4,
    }
