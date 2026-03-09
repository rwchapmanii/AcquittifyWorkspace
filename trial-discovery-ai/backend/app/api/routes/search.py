from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth import AuthContext, get_auth_context
from app.api.authz import resolve_matter_for_org
from app.api.deps import get_db
from app.services.search import hybrid_search

router = APIRouter(prefix="/matters", tags=["search"])


class SearchRequest(BaseModel):
    query: str
    limit: int = 20
    vector_limit: int = 60
    lexical_limit: int = 60


@router.post("/{matter_id}/search")
def search_matter(
    matter_id: str,
    payload: SearchRequest,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> dict:
    matter = resolve_matter_for_org(
        session=session, matter_id=matter_id, organization_id=auth.organization.id
    )
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found")

    hits = hybrid_search(
        session=session,
        matter_id=str(matter.id),
        user_id=auth.user.id,
        query=payload.query,
        limit=payload.limit,
        vector_limit=payload.vector_limit,
        lexical_limit=payload.lexical_limit,
    )
    return {"results": [hit.__dict__ for hit in hits]}
