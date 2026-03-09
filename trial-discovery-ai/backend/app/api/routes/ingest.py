from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth import AuthContext, get_auth_context
from app.api.authz import (
    require_admin_access,
    require_write_access,
    resolve_matter_for_org,
)
from app.api.deps import get_db
from app.core.config import get_settings
from app.db.models.matter import Matter
from app.services.dropbox_case_sync import sync_case_folders
from app.services.ingest import ingest_dropbox_folder

router = APIRouter(prefix="/matters", tags=["ingest"])


class IngestStartRequest(BaseModel):
    root_path: str | None = None
    case_query: str | None = None


class DropboxSyncRequest(BaseModel):
    root_path: str | None = None


def _resolve_matter(
    *, session: Session, matter_id: str, auth: AuthContext
) -> Matter | None:
    return resolve_matter_for_org(
        session=session, matter_id=matter_id, organization_id=auth.organization.id
    )


@router.post("/{matter_id}/ingest/start")
def start_ingest(
    matter_id: str,
    payload: IngestStartRequest,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_write_access),
) -> dict:
    matter = _resolve_matter(session=session, matter_id=matter_id, auth=auth)
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found")

    root_path = payload.root_path or matter.dropbox_root_path
    if not root_path:
        default_root = get_settings().dropbox_root_path
        if not default_root:
            raise HTTPException(status_code=400, detail="root_path is required")
        root_path = default_root

    case_query = payload.case_query.strip() if payload.case_query else None
    try:
        result = ingest_dropbox_folder(
            session=session,
            matter_id=str(matter.id),
            root_path=root_path,
            case_query=case_query,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    response = {"created": result.created, "skipped": result.skipped}
    if result.matched is not None:
        response["matched"] = result.matched
    return response


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


@router.get("/{matter_id}/ingest/status")
def ingest_status(
    matter_id: str,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> dict:
    matter = _resolve_matter(session=session, matter_id=matter_id, auth=auth)
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found")
    return {"matter_id": str(matter.id), "status": "not_implemented"}
