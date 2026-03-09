from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import AuthContext, get_auth_context
from app.core.config import get_settings
from app.db.models.document import Document
from app.db.models.matter import Matter

ROLE_PRECEDENCE = {
    "viewer": 10,
    "editor": 20,
    "admin": 30,
    "owner": 40,
}


def normalize_role(role: str | None) -> str:
    normalized = (role or "").strip().lower()
    if normalized not in ROLE_PRECEDENCE:
        return "viewer"
    return normalized


def has_minimum_role(role: str | None, minimum_role: str) -> bool:
    normalized_role = normalize_role(role)
    normalized_minimum = normalize_role(minimum_role)
    return ROLE_PRECEDENCE[normalized_role] >= ROLE_PRECEDENCE[normalized_minimum]


def _raise_forbidden(minimum_role: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Insufficient privileges: requires at least {minimum_role} role",
    )


def _is_admin_override_email(email: str | None) -> bool:
    normalized = (email or "").strip().lower()
    if not normalized:
        return False
    raw = get_settings().auth_admin_override_emails or ""
    allowed = {item.strip().lower() for item in raw.split(",") if item.strip()}
    return normalized in allowed


def require_view_access(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
    if not has_minimum_role(auth.membership.role, "viewer"):
        _raise_forbidden("viewer")
    return auth


def require_write_access(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
    if not has_minimum_role(auth.membership.role, "editor"):
        _raise_forbidden("editor")
    return auth


def require_admin_access(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
    if _is_admin_override_email(auth.user.email):
        return auth
    if not has_minimum_role(auth.membership.role, "admin"):
        _raise_forbidden("admin")
    return auth


def resolve_matter_for_org(
    *, session: Session, matter_id: str, organization_id: UUID
) -> Matter | None:
    matter: Matter | None = None

    try:
        matter_uuid = UUID(matter_id)
    except ValueError:
        matter_uuid = None

    if matter_uuid:
        matter = session.execute(
            select(Matter).where(
                Matter.id == matter_uuid, Matter.organization_id == organization_id
            )
        ).scalar_one_or_none()

    if not matter:
        matter = session.execute(
            select(Matter).where(
                Matter.external_id == matter_id,
                Matter.organization_id == organization_id,
            )
        ).scalar_one_or_none()

    return matter


def resolve_document_for_org(
    *,
    session: Session,
    document_id: str,
    organization_id: UUID,
    user_id: UUID | None = None,
) -> Document | None:
    try:
        document_uuid = UUID(document_id)
    except ValueError:
        return None

    query = (
        select(Document)
        .join(Matter, Matter.id == Document.matter_id)
        .where(Document.id == document_uuid, Matter.organization_id == organization_id)
    )
    if user_id:
        query = query.where(Document.uploaded_by_user_id == user_id)

    return session.execute(query).scalar_one_or_none()
