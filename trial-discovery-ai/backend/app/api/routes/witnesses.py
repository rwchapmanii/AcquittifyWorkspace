from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.auth import AuthContext, get_auth_context
from app.api.authz import resolve_matter_for_org
from app.api.deps import get_db
from app.services.witnesses import list_witness_documents, list_witnesses

router = APIRouter(prefix="/matters", tags=["witnesses"])


@router.get("/{matter_id}/witnesses")
def get_witnesses(
    matter_id: str,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> dict:
    matter = resolve_matter_for_org(
        session=session, matter_id=matter_id, organization_id=auth.organization.id
    )
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found")
    witnesses = list_witnesses(
        session=session,
        matter_id=str(matter.id),
        user_id=auth.user.id,
    )
    return {"witnesses": [w.__dict__ for w in witnesses]}


@router.get("/{matter_id}/witnesses/{entity_id}/documents")
def get_witness_documents(
    matter_id: str,
    entity_id: str,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> dict:
    matter = resolve_matter_for_org(
        session=session, matter_id=matter_id, organization_id=auth.organization.id
    )
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found")

    documents = list_witness_documents(
        session=session,
        matter_id=str(matter.id),
        entity_id=entity_id,
        user_id=auth.user.id,
    )
    return {"documents": [d.__dict__ for d in documents]}
