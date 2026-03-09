import hashlib
from typing import Optional

from fastapi import HTTPException, Request

from .db import get_conn


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}{password}".encode("utf-8")).hexdigest()


def verify_password(password: str, stored_hash: str) -> bool:
    if "$" not in stored_hash:
        return False
    salt, digest = stored_hash.split("$", 1)
    return _hash_password(password, salt) == digest


def authenticate_user(username: str, password: str) -> Optional[dict]:
    with get_conn(write=False) as conn:
        row = conn.execute(
            """
            SELECT id, username, password_hash, role
            FROM derived.admin_user
            WHERE username = %s
            """,
            (username,),
        ).fetchone()
    if not row or not verify_password(password, row[2]):
        return None
    return {"id": row[0], "username": row[1], "role": row[3]}


def get_current_user(request: Request) -> dict:
    user = request.session.get("user") if hasattr(request, "session") else None
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def require_role(role: str):
    def _guard(request: Request) -> dict:
        user = get_current_user(request)
        if user["role"] != role and user["role"] != "admin_reviewer":
            raise HTTPException(status_code=403, detail="Insufficient role")
        return user

    return _guard
