from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.auth import AuthContext, get_auth_context
from app.api.authz import resolve_matter_for_org
from app.api.deps import get_db
from app.services.exhibits import export_exhibits_csv, list_exhibits

router = APIRouter(prefix="/matters", tags=["exhibits"])


@router.get("/{matter_id}/exhibits")
def get_exhibits(
    matter_id: str,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> dict:
    matter = resolve_matter_for_org(
        session=session, matter_id=matter_id, organization_id=auth.organization.id
    )
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found")
    rows = list_exhibits(
        session=session,
        matter_id=str(matter.id),
        user_id=auth.user.id,
    )
    return {"exhibits": [row.__dict__ for row in rows]}


@router.post("/{matter_id}/exhibits/export")
def export_exhibits(
    matter_id: str,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> Response:
    matter = resolve_matter_for_org(
        session=session, matter_id=matter_id, organization_id=auth.organization.id
    )
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found")
    rows = list_exhibits(
        session=session,
        matter_id=str(matter.id),
        user_id=auth.user.id,
    )
    csv_data = export_exhibits_csv(rows)
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=exhibits.csv"},
    )
