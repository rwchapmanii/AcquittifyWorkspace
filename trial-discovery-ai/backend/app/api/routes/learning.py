from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.auth import AuthContext
from app.api.authz import require_admin_access, resolve_matter_for_org
from app.api.deps import get_db
from app.services.learning import rescore_priorities

router = APIRouter(prefix="/matters", tags=["learning"])


@router.post("/{matter_id}/priorities/rescore")
def rescore(
    matter_id: str,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_admin_access),
) -> dict:
    matter = resolve_matter_for_org(
        session=session, matter_id=matter_id, organization_id=auth.organization.id
    )
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found")
    result = rescore_priorities(
        session=session,
        matter_id=str(matter.id),
        user_id=str(auth.user.id),
    )
    return {"rescored": result.rescored}
