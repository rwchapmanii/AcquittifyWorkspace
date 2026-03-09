from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.security import decode_access_token, generate_secret_token
from app.db.models.membership import Membership
from app.db.models.organization import Organization
from app.db.models.user import User

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    user: User
    organization: Organization
    membership: Membership


def _auth_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
    )


def set_auth_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        domain=settings.auth_cookie_domain,
        max_age=settings.auth_access_token_exp_minutes * 60,
        path="/",
    )


def set_csrf_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.auth_csrf_cookie_name,
        value=token,
        httponly=False,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        domain=settings.auth_cookie_domain,
        max_age=settings.auth_access_token_exp_minutes * 60,
        path="/",
    )


def ensure_csrf_cookie(request: Request, response: Response) -> str:
    settings = get_settings()
    csrf_token = request.cookies.get(settings.auth_csrf_cookie_name)
    if not csrf_token:
        csrf_token = generate_secret_token()
        set_csrf_cookie(response, csrf_token)
    return csrf_token


def clear_auth_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=settings.auth_cookie_name,
        domain=settings.auth_cookie_domain,
        path="/",
    )


def clear_csrf_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=settings.auth_csrf_cookie_name,
        domain=settings.auth_cookie_domain,
        path="/",
    )


def get_auth_context(
    request: Request,
    session: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> AuthContext:
    settings = get_settings()
    token = None
    if credentials and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    if not token:
        token = request.cookies.get(settings.auth_cookie_name)
    if not token:
        raise _auth_error()

    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise _auth_error() from exc

    sub = payload.get("sub")
    org = payload.get("org")
    if not isinstance(sub, str) or not isinstance(org, str):
        raise _auth_error()

    try:
        user_id = UUID(sub)
        organization_id = UUID(org)
    except ValueError as exc:
        raise _auth_error() from exc

    user = session.get(User, user_id)
    if not user or not user.is_active:
        raise _auth_error()

    membership = session.execute(
        select(Membership).where(
            Membership.user_id == user_id, Membership.organization_id == organization_id
        )
    ).scalar_one_or_none()
    if not membership:
        raise _auth_error()

    organization = session.get(Organization, organization_id)
    if not organization:
        raise _auth_error()

    return AuthContext(user=user, organization=organization, membership=membership)
