from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.auth import AuthContext, get_auth_context
from app.api.authz import resolve_matter_for_org
from app.api.deps import get_db
from app.services.ontology import build_caselaw_ontology_graph, build_matter_ontology_graph

router = APIRouter(prefix="/matters", tags=["ontology"])


def _resolve_view_mode(*, request: Request, view: str | None) -> str:
    if view in {"casefile", "caselaw"}:
        return view
    referer = (request.headers.get("referer") or "").strip()
    if not referer:
        return "casefile"
    parsed = urlparse(referer)
    query = parse_qs(parsed.query)
    referer_view = ((query.get("view") or [None])[0] or "").strip().lower()
    if referer_view == "caselaw":
        return "caselaw"
    return "casefile"


@router.get("/{matter_id}/ontology")
def get_matter_ontology(
    request: Request,
    matter_id: str,
    view: str | None = Query(default=None, pattern="^(casefile|caselaw)$"),
    max_documents: int = Query(default=2500, ge=1, le=10000),
    include_statement_nodes: bool = True,
    include_evidence_nodes: bool = True,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> dict:
    matter = resolve_matter_for_org(
        session=session, matter_id=matter_id, organization_id=auth.organization.id
    )
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found")

    resolved_view = _resolve_view_mode(request=request, view=view)
    if resolved_view == "caselaw":
        graph = build_caselaw_ontology_graph(
            session=session,
            matter_id=str(matter.id),
            max_cases=max_documents,
        )
    else:
        graph = build_matter_ontology_graph(
            session=session,
            matter_id=str(matter.id),
            max_documents=max_documents,
            include_statement_nodes=include_statement_nodes,
            include_evidence_nodes=include_evidence_nodes,
        )
    return graph
