from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import AliasChoices, BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth import (
    AuthContext,
    clear_auth_cookie,
    clear_csrf_cookie,
    ensure_csrf_cookie,
    get_auth_context,
    set_auth_cookie,
    set_csrf_cookie,
)
from app.api.authz import normalize_role
from app.api.deps import get_db
from app.core.config import get_settings
from app.core.security import (
    build_totp_uri,
    create_access_token,
    decrypt_sensitive_value,
    encrypt_sensitive_value,
    generate_backup_codes,
    generate_numeric_code,
    generate_secret_token,
    generate_totp_secret,
    hash_backup_code,
    hash_password,
    hash_reset_token,
    normalize_email,
    pwd_context,
    validate_password_strength,
    verify_password,
    verify_totp_code,
)
from app.db.models.auth_login_challenge import AuthLoginChallenge
from app.db.models.membership import Membership
from app.db.models.organization import Organization
from app.db.models.password_reset_token import PasswordResetToken
from app.db.models.user import User
from app.services.emailer import EmailDeliveryError, send_password_reset_code
from app.services.usage_metrics import record_login_success, record_password_reset

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str | None = None
    organization_name: str | None = None


class LoginRequest(BaseModel):
    email: str = Field(validation_alias=AliasChoices("email", "username_or_email"))
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str = Field(validation_alias=AliasChoices("token", "code", "reset_code"))
    new_password: str


class MFALoginVerifyRequest(BaseModel):
    ticket: str = Field(validation_alias=AliasChoices("ticket", "mfa_ticket"))
    code: str


class MFASetupVerifyRequest(BaseModel):
    code: str


class MFADisableRequest(BaseModel):
    password: str
    code: str


class MFARecoveryCodesRegenerateRequest(BaseModel):
    code: str


def _serialize_auth_context(auth: AuthContext) -> dict:
    return {
        "user": {
            "id": str(auth.user.id),
            "email": auth.user.email,
            "full_name": auth.user.full_name,
            "mfa_enabled": bool(auth.user.mfa_enabled),
        },
        "organization": {
            "id": str(auth.organization.id),
            "name": auth.organization.name,
        },
        "role": normalize_role(auth.membership.role),
    }


def _resolve_default_membership(
    *, session: Session, user_id: UUID
) -> tuple[Membership, Organization]:
    membership = session.execute(
        select(Membership)
        .where(Membership.user_id == user_id)
        .order_by(Membership.created_at.asc())
    ).scalar_one_or_none()
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No organization membership assigned",
        )
    organization = session.get(Organization, membership.organization_id)
    if not organization:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization not found",
        )
    return membership, organization


def _validate_password_or_raise(password: str) -> None:
    problem = validate_password_strength(password)
    if problem:
        raise HTTPException(status_code=400, detail=problem)


def _backup_hashes(user: User) -> list[str]:
    raw = user.mfa_backup_codes_hashes
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if isinstance(item, str)]


def _verify_user_mfa_code(*, user: User, code: str) -> tuple[bool, bool]:
    code_value = code.strip()
    if not code_value:
        return False, False
    if not user.mfa_secret_enc:
        return False, False
    try:
        secret = decrypt_sensitive_value(user.mfa_secret_enc)
    except ValueError:
        return False, False

    if verify_totp_code(secret=secret, code=code_value):
        return True, False

    hashed = hash_backup_code(code_value)
    hashes = _backup_hashes(user)
    if hashed in hashes:
        hashes.remove(hashed)
        user.mfa_backup_codes_hashes = hashes
        return True, True
    return False, False


@router.post("/register")
def register(
    payload: RegisterRequest,
    response: Response,
    session: Session = Depends(get_db),
) -> dict:
    email = normalize_email(payload.email)
    if len(email) < 3:
        raise HTTPException(status_code=400, detail="Username or email is too short")
    _validate_password_or_raise(payload.password)

    existing = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Email is already registered")

    org_name = (payload.organization_name or "").strip()
    if not org_name:
        org_name = f"{(payload.full_name or email.split('@')[0]).strip()}'s Organization"

    has_users = session.execute(select(User.id).limit(1)).scalar_one_or_none() is not None
    if has_users:
        organization = Organization(name=org_name)
        session.add(organization)
        session.flush()
    else:
        organization = session.execute(
            select(Organization).order_by(Organization.created_at.asc())
        ).scalar_one_or_none()
        if not organization:
            organization = Organization(name=org_name)
            session.add(organization)
            session.flush()
        elif payload.organization_name and payload.organization_name.strip():
            organization.name = payload.organization_name.strip()

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=(payload.full_name or "").strip() or None,
        is_active=True,
    )
    session.add(user)
    session.flush()

    membership = Membership(
        organization_id=organization.id,
        user_id=user.id,
        role="owner",
    )
    session.add(membership)
    record_login_success(
        session=session,
        user_id=user.id,
        organization_id=organization.id,
    )
    session.commit()
    session.refresh(user)
    session.refresh(organization)
    session.refresh(membership)

    token = create_access_token(user_id=user.id, organization_id=organization.id)
    set_auth_cookie(response, token)
    set_csrf_cookie(response, generate_secret_token())
    return _serialize_auth_context(
        AuthContext(user=user, organization=organization, membership=membership)
    )


@router.post("/login")
def login(
    payload: LoginRequest,
    response: Response,
    session: Session = Depends(get_db),
) -> dict:
    email = normalize_email(payload.email)
    user = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User is inactive")

    password_needs_upgrade = pwd_context.needs_update(user.password_hash)
    if password_needs_upgrade:
        user.password_hash = hash_password(payload.password)
        session.add(user)

    membership, organization = _resolve_default_membership(session=session, user_id=user.id)

    if user.mfa_enabled and user.mfa_secret_enc:
        settings = get_settings()
        now_utc = datetime.now(timezone.utc)
        session.execute(
            AuthLoginChallenge.__table__.delete().where(
                AuthLoginChallenge.user_id == user.id,
                AuthLoginChallenge.expires_at < now_utc - timedelta(days=30),
            )
        )
        plain_ticket = generate_secret_token()
        challenge = AuthLoginChallenge(
            user_id=user.id,
            organization_id=organization.id,
            ticket_hash=hash_reset_token(plain_ticket),
            expires_at=now_utc
            + timedelta(minutes=settings.auth_mfa_challenge_exp_minutes),
        )
        session.add(challenge)
        session.commit()
        return {
            "status": "mfa_required",
            "mfa_required": True,
            "mfa_ticket": plain_ticket,
            "expires_at": challenge.expires_at.isoformat(),
            "methods": ["totp", "backup_code"],
        }

    record_login_success(
        session=session,
        user_id=user.id,
        organization_id=organization.id,
    )
    session.commit()
    session.refresh(user)
    token = create_access_token(user_id=user.id, organization_id=organization.id)
    set_auth_cookie(response, token)
    set_csrf_cookie(response, generate_secret_token())
    return _serialize_auth_context(
        AuthContext(user=user, organization=organization, membership=membership)
    )


@router.post("/mfa/login/verify")
def verify_mfa_login(
    payload: MFALoginVerifyRequest,
    response: Response,
    session: Session = Depends(get_db),
) -> dict:
    ticket = payload.ticket.strip()
    if not ticket:
        raise HTTPException(status_code=400, detail="MFA ticket is required")
    code = payload.code.strip()
    if not code:
        raise HTTPException(status_code=400, detail="MFA code is required")

    now_utc = datetime.now(timezone.utc)
    challenge = session.execute(
        select(AuthLoginChallenge).where(
            AuthLoginChallenge.ticket_hash == hash_reset_token(ticket),
            AuthLoginChallenge.consumed_at.is_(None),
            AuthLoginChallenge.expires_at > now_utc,
        )
    ).scalar_one_or_none()
    if not challenge:
        raise HTTPException(status_code=400, detail="Invalid or expired MFA challenge")

    settings = get_settings()
    if challenge.attempts >= settings.auth_mfa_challenge_max_attempts:
        challenge.consumed_at = now_utc
        session.commit()
        raise HTTPException(status_code=401, detail="MFA attempts exceeded")

    user = session.get(User, challenge.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid authentication session")
    organization = session.get(Organization, challenge.organization_id)
    if not organization:
        raise HTTPException(status_code=401, detail="Invalid authentication session")
    membership = session.execute(
        select(Membership).where(
            Membership.user_id == user.id,
            Membership.organization_id == organization.id,
        )
    ).scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=401, detail="Invalid authentication session")

    valid, used_backup = _verify_user_mfa_code(user=user, code=code)
    if not valid:
        challenge.attempts += 1
        if challenge.attempts >= settings.auth_mfa_challenge_max_attempts:
            challenge.consumed_at = now_utc
        session.commit()
        raise HTTPException(status_code=401, detail="Invalid MFA code")

    challenge.consumed_at = now_utc
    user.mfa_last_verified_at = now_utc
    record_login_success(
        session=session,
        user_id=user.id,
        organization_id=organization.id,
    )
    session.commit()
    session.refresh(user)

    token = create_access_token(user_id=user.id, organization_id=organization.id)
    set_auth_cookie(response, token)
    set_csrf_cookie(response, generate_secret_token())
    response_data = _serialize_auth_context(
        AuthContext(user=user, organization=organization, membership=membership)
    )
    response_data["mfa_verified"] = True
    response_data["used_backup_code"] = used_backup
    return response_data


@router.post("/logout")
def logout(response: Response) -> dict:
    clear_auth_cookie(response)
    clear_csrf_cookie(response)
    return {"status": "ok"}


@router.get("/me")
def me(
    request: Request,
    response: Response,
    auth: AuthContext = Depends(get_auth_context),
) -> dict:
    ensure_csrf_cookie(request, response)
    return _serialize_auth_context(auth)


@router.post("/password/forgot")
def forgot_password(
    payload: ForgotPasswordRequest,
    session: Session = Depends(get_db),
) -> dict:
    email = normalize_email(payload.email)
    user = session.execute(
        select(User).where(User.email == email, User.is_active.is_(True))
    ).scalar_one_or_none()

    response = {
        "status": "ok",
        "message": "If the account exists, a reset code has been sent.",
    }
    if not user:
        return response

    now_utc = datetime.now(timezone.utc)
    outstanding = session.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.consumed_at.is_(None),
        )
    ).scalars().all()
    for token in outstanding:
        token.consumed_at = now_utc

    settings = get_settings()
    code = generate_numeric_code(settings.auth_password_reset_code_length)
    expires_at = now_utc + timedelta(
        minutes=settings.auth_password_reset_token_exp_minutes
    )
    reset_token = PasswordResetToken(
        user_id=user.id,
        token_hash=hash_reset_token(code),
        expires_at=expires_at,
    )
    session.add(reset_token)

    try:
        send_password_reset_code(
            recipient_email=user.email,
            reset_code=code,
            expires_minutes=settings.auth_password_reset_token_exp_minutes,
        )
    except EmailDeliveryError:
        if not settings.auth_password_reset_dev_return_token:
            raise HTTPException(
                status_code=503, detail="Password reset email service unavailable"
            ) from None

    session.commit()

    if settings.auth_password_reset_dev_return_token:
        response["reset_code"] = code
        response["reset_token"] = code
        response["expires_at"] = expires_at.isoformat()
    return response


@router.post("/password/reset")
def reset_password(
    payload: ResetPasswordRequest,
    session: Session = Depends(get_db),
) -> dict:
    _validate_password_or_raise(payload.new_password)

    token = payload.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="Reset code is required")

    now_utc = datetime.now(timezone.utc)
    record = session.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == hash_reset_token(token),
            PasswordResetToken.consumed_at.is_(None),
            PasswordResetToken.expires_at > now_utc,
        )
    ).scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=400, detail="Invalid or expired password reset code")

    user = session.get(User, record.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=400, detail="Invalid or expired password reset code")

    membership = session.execute(
        select(Membership)
        .where(Membership.user_id == user.id)
        .order_by(Membership.created_at.asc())
    ).scalar_one_or_none()

    user.password_hash = hash_password(payload.new_password)
    record.consumed_at = now_utc
    if membership:
        record_password_reset(
            session=session,
            user_id=user.id,
            organization_id=membership.organization_id,
        )
    session.commit()
    return {"status": "ok"}


@router.get("/mfa/status")
def mfa_status(auth: AuthContext = Depends(get_auth_context)) -> dict:
    return {
        "enabled": bool(auth.user.mfa_enabled and auth.user.mfa_secret_enc),
        "pending_setup": bool(auth.user.mfa_pending_secret_enc),
    }


@router.post("/mfa/setup")
def mfa_setup(
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> dict:
    user = session.get(User, auth.user.id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Authentication required")
    if user.mfa_enabled and user.mfa_secret_enc:
        raise HTTPException(status_code=409, detail="MFA is already enabled")

    secret = generate_totp_secret()
    issuer = get_settings().auth_mfa_issuer
    uri = build_totp_uri(secret=secret, account_name=user.email, issuer=issuer)
    user.mfa_pending_secret_enc = encrypt_sensitive_value(secret)
    session.add(user)
    session.commit()
    return {
        "status": "ok",
        "issuer": issuer,
        "account_name": user.email,
        "secret": secret,
        "otpauth_uri": uri,
    }


@router.post("/mfa/setup/verify")
def mfa_setup_verify(
    payload: MFASetupVerifyRequest,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> dict:
    user = session.get(User, auth.user.id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not user.mfa_pending_secret_enc:
        raise HTTPException(status_code=400, detail="No pending MFA setup")

    try:
        secret = decrypt_sensitive_value(user.mfa_pending_secret_enc)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid pending MFA setup") from None

    if not verify_totp_code(secret=secret, code=payload.code):
        raise HTTPException(status_code=400, detail="Invalid MFA code")

    settings = get_settings()
    now_utc = datetime.now(timezone.utc)
    backup_codes = generate_backup_codes(count=settings.auth_mfa_backup_code_count)
    user.mfa_secret_enc = encrypt_sensitive_value(secret)
    user.mfa_pending_secret_enc = None
    user.mfa_enabled = True
    user.mfa_backup_codes_hashes = [hash_backup_code(code) for code in backup_codes]
    user.mfa_enrolled_at = now_utc
    user.mfa_last_verified_at = now_utc
    session.add(user)
    session.commit()
    return {
        "status": "ok",
        "mfa_enabled": True,
        "backup_codes": backup_codes,
    }


@router.post("/mfa/disable")
def mfa_disable(
    payload: MFADisableRequest,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> dict:
    user = session.get(User, auth.user.id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Authentication required")

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid password")
    valid, _used_backup = _verify_user_mfa_code(user=user, code=payload.code)
    if not valid:
        raise HTTPException(status_code=400, detail="Invalid MFA code")

    user.mfa_enabled = False
    user.mfa_secret_enc = None
    user.mfa_pending_secret_enc = None
    user.mfa_backup_codes_hashes = []
    user.mfa_enrolled_at = None
    user.mfa_last_verified_at = None
    session.add(user)
    session.commit()
    return {"status": "ok", "mfa_enabled": False}


@router.post("/mfa/recovery-codes/regenerate")
def mfa_regenerate_recovery_codes(
    payload: MFARecoveryCodesRegenerateRequest,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> dict:
    user = session.get(User, auth.user.id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not user.mfa_enabled or not user.mfa_secret_enc:
        raise HTTPException(status_code=400, detail="MFA is not enabled")

    valid, _used_backup = _verify_user_mfa_code(user=user, code=payload.code)
    if not valid:
        raise HTTPException(status_code=400, detail="Invalid MFA code")

    backup_codes = generate_backup_codes(count=get_settings().auth_mfa_backup_code_count)
    user.mfa_backup_codes_hashes = [hash_backup_code(code) for code in backup_codes]
    user.mfa_last_verified_at = datetime.now(timezone.utc)
    session.add(user)
    session.commit()
    return {"status": "ok", "backup_codes": backup_codes}


@router.get("/usage")
def get_usage(
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> dict:
    from app.db.models.document import Document
    from app.db.models.user_account_metric import UserAccountMetric

    metric = session.get(UserAccountMetric, auth.user.id)
    live_storage = session.execute(
        select(
            func.coalesce(func.sum(Document.file_size), 0).label("storage_bytes"),
            func.count(Document.id).label("document_count"),
        ).where(Document.uploaded_by_user_id == auth.user.id)
    ).one()

    return {
        "user_id": str(auth.user.id),
        "organization_id": str(auth.organization.id),
        "storage": {
            "bytes_live": int(live_storage.storage_bytes or 0),
            "documents_live": int(live_storage.document_count or 0),
            "bytes_metered": int(metric.total_storage_bytes) if metric else 0,
            "uploads_bytes_total": int(metric.total_upload_bytes) if metric else 0,
            "documents_metered_total": int(metric.total_documents) if metric else 0,
        },
        "agent": {
            "requests_total": int(metric.total_agent_requests) if metric else 0,
            "prompt_tokens_total": int(metric.total_agent_prompt_tokens) if metric else 0,
            "completion_tokens_total": int(metric.total_agent_completion_tokens)
            if metric
            else 0,
            "tokens_total": int(metric.total_agent_tokens) if metric else 0,
        },
        "auth": {
            "logins_total": int(metric.total_logins) if metric else 0,
            "password_resets_total": int(metric.total_password_resets) if metric else 0,
            "mfa_enabled": bool(auth.user.mfa_enabled and auth.user.mfa_secret_enc),
        },
        "last_activity_at": (
            metric.last_activity_at.isoformat() if metric and metric.last_activity_at else None
        ),
    }
