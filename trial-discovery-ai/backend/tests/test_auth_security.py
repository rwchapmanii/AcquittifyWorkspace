import uuid

from fastapi.testclient import TestClient
import pyotp
from sqlalchemy.orm import Session

import app.main as app_main
from app.core.security import hash_password
from app.db.models.membership import Membership
from app.db.models.user import User


def _csrf_headers(client: TestClient) -> dict[str, str]:
    token = client.cookies.get("peregrine_csrf")
    assert token
    return {"X-CSRF-Token": token}


def _register(
    client: TestClient,
    *,
    email: str,
    password: str = "password123",
    full_name: str | None = None,
) -> dict:
    payload: dict[str, str] = {"email": email, "password": password}
    if full_name:
        payload["full_name"] = full_name
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def _login(
    client: TestClient,
    *,
    email: str,
    password: str,
    ip_address: str,
):
    return client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"x-forwarded-for": ip_address},
    )


def _create_member(
    session: Session,
    *,
    email: str,
    password: str,
    organization_id: str,
    role: str,
) -> None:
    user = User(
        email=email,
        password_hash=hash_password(password),
        full_name=role,
        is_active=True,
    )
    session.add(user)
    session.flush()

    membership = Membership(
        organization_id=uuid.UUID(organization_id),
        user_id=user.id,
        role=role,
    )
    session.add(membership)
    session.commit()


def test_csrf_required_for_mutating_endpoints(client: TestClient) -> None:
    email = f"csrf-{uuid.uuid4().hex}@example.test"
    _register(client, email=email)

    missing_csrf = client.post(
        "/matters",
        json={"name": "No CSRF"},
        headers={"origin": "http://localhost:3000"},
    )
    assert missing_csrf.status_code == 403
    assert missing_csrf.json()["detail"] == "CSRF token missing or invalid"
    assert missing_csrf.headers.get("access-control-allow-origin") == "http://localhost:3000"

    with_csrf = client.post(
        "/matters",
        json={"name": "With CSRF"},
        headers=_csrf_headers(client),
    )
    assert with_csrf.status_code == 200


def test_rbac_blocks_viewer_and_allows_editor(
    client: TestClient, db_session: Session
) -> None:
    owner_email = f"owner-{uuid.uuid4().hex}@example.test"
    owner_data = _register(client, email=owner_email)
    organization_id = owner_data["organization"]["id"]

    viewer_email = f"viewer-{uuid.uuid4().hex}@example.test"
    editor_email = f"editor-{uuid.uuid4().hex}@example.test"
    _create_member(
        db_session,
        email=viewer_email,
        password="password123",
        organization_id=organization_id,
        role="viewer",
    )
    _create_member(
        db_session,
        email=editor_email,
        password="password123",
        organization_id=organization_id,
        role="editor",
    )

    client.cookies.clear()
    viewer_login = _login(
        client,
        email=viewer_email,
        password="password123",
        ip_address="198.51.100.10",
    )
    assert viewer_login.status_code == 200
    assert viewer_login.json()["role"] == "viewer"

    viewer_create = client.post(
        "/matters",
        json={"name": "Viewer should fail"},
        headers=_csrf_headers(client),
    )
    assert viewer_create.status_code == 403

    client.cookies.clear()
    editor_login = _login(
        client,
        email=editor_email,
        password="password123",
        ip_address="198.51.100.11",
    )
    assert editor_login.status_code == 200
    assert editor_login.json()["role"] == "editor"

    editor_create = client.post(
        "/matters",
        json={"name": "Editor can create"},
        headers=_csrf_headers(client),
    )
    assert editor_create.status_code == 200


def test_password_reset_flow(client: TestClient) -> None:
    email = f"reset-{uuid.uuid4().hex}@example.test"
    old_password = "password123"
    new_password = "new-password-123"
    _register(client, email=email, password=old_password)

    forgot = client.post(
        "/auth/password/forgot",
        json={"email": email},
        headers={"x-forwarded-for": "203.0.113.20"},
    )
    assert forgot.status_code == 200
    body = forgot.json()
    assert body["status"] == "ok"
    reset_code = body.get("reset_code")
    assert isinstance(reset_code, str) and reset_code

    reset = client.post(
        "/auth/password/reset",
        json={"code": reset_code, "new_password": new_password},
        headers={"x-forwarded-for": "203.0.113.21"},
    )
    assert reset.status_code == 200

    client.cookies.clear()
    old_login = _login(
        client,
        email=email,
        password=old_password,
        ip_address="203.0.113.22",
    )
    assert old_login.status_code == 401

    new_login = _login(
        client,
        email=email,
        password=new_password,
        ip_address="203.0.113.23",
    )
    assert new_login.status_code == 200


def test_mfa_setup_and_login_challenge_flow(client: TestClient) -> None:
    email = f"mfa-{uuid.uuid4().hex}@example.test"
    password = "password123"
    _register(client, email=email, password=password)

    setup = client.post("/auth/mfa/setup", headers=_csrf_headers(client))
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    assert isinstance(secret, str) and secret

    totp_code = pyotp.TOTP(secret).now()
    verify_setup = client.post(
        "/auth/mfa/setup/verify",
        json={"code": totp_code},
        headers=_csrf_headers(client),
    )
    assert verify_setup.status_code == 200, verify_setup.text
    backup_codes = verify_setup.json().get("backup_codes")
    assert isinstance(backup_codes, list) and backup_codes

    client.cookies.clear()
    login = _login(
        client,
        email=email,
        password=password,
        ip_address="198.51.100.50",
    )
    assert login.status_code == 200, login.text
    login_body = login.json()
    assert login_body.get("mfa_required") is True
    ticket = login_body.get("mfa_ticket")
    assert isinstance(ticket, str) and ticket

    verify_login = client.post(
        "/auth/mfa/login/verify",
        json={"ticket": ticket, "code": pyotp.TOTP(secret).now()},
        headers={"x-forwarded-for": "198.51.100.51"},
    )
    assert verify_login.status_code == 200, verify_login.text
    verified_body = verify_login.json()
    assert verified_body.get("mfa_verified") is True
    assert verified_body["user"]["email"] == email


def test_rate_limit_on_login(client: TestClient) -> None:
    limiter = app_main.auth_rate_limiter
    original_max_attempts = limiter.max_attempts
    limiter.max_attempts = 2

    try:
        ip_header = {"x-forwarded-for": "192.0.2.200"}
        first = client.post(
            "/auth/login",
            json={"email": "nobody@example.test", "password": "wrong"},
            headers=ip_header,
        )
        second = client.post(
            "/auth/login",
            json={"email": "nobody@example.test", "password": "wrong"},
            headers=ip_header,
        )
        third = client.post(
            "/auth/login",
            json={"email": "nobody@example.test", "password": "wrong"},
            headers=ip_header,
        )

        assert first.status_code == 401
        assert second.status_code == 401
        assert third.status_code == 429
        assert third.json()["detail"] == "Too many requests. Please try again later."
    finally:
        limiter.max_attempts = original_max_attempts


def test_rate_limit_response_includes_cors_and_retry_headers(client: TestClient) -> None:
    limiter = app_main.auth_rate_limiter
    original_max_attempts = limiter.max_attempts
    limiter.max_attempts = 0

    try:
        response = client.post(
            "/auth/login",
            json={"email": "nobody@example.test", "password": "wrong"},
            headers={
                "x-forwarded-for": "192.0.2.250",
                "origin": "http://localhost:3000",
            },
        )
        assert response.status_code == 429
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
        assert response.headers.get("access-control-expose-headers") == "Retry-After"
        assert response.headers.get("retry-after")
    finally:
        limiter.max_attempts = original_max_attempts
