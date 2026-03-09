import base64
import hashlib
import hmac
import json
import re
import secrets
import string
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pyotp
from cryptography.fernet import Fernet, InvalidToken
from passlib.context import CryptContext
from passlib.exc import UnknownHashError

from app.core.config import get_settings

pwd_context = CryptContext(
    schemes=["pbkdf2_sha256", "bcrypt"],
    deprecated="auto",
)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return pwd_context.verify(plain_password, password_hash)
    except (ValueError, UnknownHashError):
        return False


def validate_password_strength(password: str) -> str | None:
    settings = get_settings()
    if len(password) < settings.auth_password_min_length:
        return f"Password must be at least {settings.auth_password_min_length} characters"
    if settings.auth_password_require_upper and not re.search(r"[A-Z]", password):
        return "Password must include at least one uppercase letter"
    if settings.auth_password_require_lower and not re.search(r"[a-z]", password):
        return "Password must include at least one lowercase letter"
    if settings.auth_password_require_number and not re.search(r"[0-9]", password):
        return "Password must include at least one number"
    if settings.auth_password_require_symbol and not re.search(r"[^A-Za-z0-9]", password):
        return "Password must include at least one symbol"
    return None


def generate_secret_token() -> str:
    return secrets.token_urlsafe(32)


def generate_numeric_code(length: int) -> str:
    safe_length = max(4, min(12, int(length)))
    upper = 10**safe_length
    return f"{secrets.randbelow(upper):0{safe_length}d}"


def hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(*, user_id: UUID, organization_id: UUID) -> str:
    settings = get_settings()
    expires = datetime.now(timezone.utc) + timedelta(
        minutes=settings.auth_access_token_exp_minutes
    )
    payload = {
        "sub": str(user_id),
        "org": str(organization_id),
        "exp": int(expires.timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp()),
    }
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    payload_b64 = _b64url_encode(payload_json)
    signature = hmac.new(
        settings.auth_secret_key.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return f"{payload_b64}.{_b64url_encode(signature)}"


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    parts = token.split(".")
    if len(parts) != 2:
        raise ValueError("Invalid token")

    payload_b64, signature_b64 = parts
    expected_signature = hmac.new(
        settings.auth_secret_key.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    try:
        provided_signature = _b64url_decode(signature_b64)
    except ValueError as exc:
        raise ValueError("Invalid token") from exc

    if not hmac.compare_digest(expected_signature, provided_signature):
        raise ValueError("Invalid token")

    try:
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("Invalid token") from exc

    exp = payload.get("exp")
    if not isinstance(exp, int):
        raise ValueError("Invalid token")
    if datetime.now(timezone.utc).timestamp() > exp:
        raise ValueError("Token expired")

    return payload


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def build_totp_uri(*, secret: str, account_name: str, issuer: str | None = None) -> str:
    resolved_issuer = (issuer or get_settings().auth_mfa_issuer).strip() or "Acquittify"
    return pyotp.TOTP(secret).provisioning_uri(
        name=account_name,
        issuer_name=resolved_issuer,
    )


def verify_totp_code(*, secret: str, code: str) -> bool:
    normalized = "".join(ch for ch in code if ch.isdigit())
    if len(normalized) < 6:
        return False
    return bool(pyotp.TOTP(secret).verify(normalized, valid_window=1))


def generate_backup_codes(*, count: int) -> list[str]:
    safe_count = max(4, min(20, int(count)))
    alphabet = string.ascii_uppercase + string.digits
    codes: list[str] = []
    for _ in range(safe_count):
        raw = "".join(secrets.choice(alphabet) for _ in range(10))
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes


def hash_backup_code(code: str) -> str:
    settings = get_settings()
    normalized = code.strip().upper()
    digest = hmac.new(
        settings.auth_secret_key.encode("utf-8"),
        normalized.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest


def encrypt_sensitive_value(value: str) -> str:
    return _get_fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_sensitive_value(token: str) -> str:
    try:
        return _get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Invalid encrypted value") from exc


def _get_fernet() -> Fernet:
    settings = get_settings()
    key_material = hashlib.sha256(settings.auth_secret_key.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(key_material)
    return Fernet(key)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
