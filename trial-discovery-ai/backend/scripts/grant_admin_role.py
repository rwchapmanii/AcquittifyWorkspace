#!/usr/bin/env python3
from __future__ import annotations

import argparse
from typing import Iterable

from sqlalchemy import select

from app.api.authz import normalize_role
from app.db.models.membership import Membership
from app.db.models.organization import Organization
from app.db.models.user import User
from app.db.session import get_session_factory

VALID_ROLES = ("viewer", "editor", "admin", "owner")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Grant admin/owner-level membership role to a user email."
    )
    parser.add_argument("--email", required=True, help="User email")
    parser.add_argument(
        "--role",
        default="admin",
        choices=VALID_ROLES,
        help="Membership role to assign (default: admin)",
    )
    return parser.parse_args()


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def _pick_default_org_id(session):
    org = session.execute(select(Organization).order_by(Organization.created_at.asc())).scalar_one_or_none()
    return org.id if org else None


def _user_memberships(session, user_id) -> Iterable[Membership]:
    return session.execute(select(Membership).where(Membership.user_id == user_id)).scalars().all()


def main() -> int:
    args = parse_args()
    email = _normalize_email(args.email)
    target_role = normalize_role(args.role)
    if target_role not in VALID_ROLES:
        raise SystemExit(f"Invalid role: {args.role}")

    session_factory = get_session_factory()
    with session_factory() as session:
        user = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if not user:
            raise SystemExit(f"User not found: {email}")

        memberships = list(_user_memberships(session, user.id))
        if not memberships:
            org_id = _pick_default_org_id(session)
            if not org_id:
                raise SystemExit("No organization found to attach membership")
            memberships = [
                Membership(
                    organization_id=org_id,
                    user_id=user.id,
                    role=target_role,
                )
            ]
            session.add(memberships[0])

        updated = 0
        for membership in memberships:
            if normalize_role(membership.role) != target_role:
                membership.role = target_role
                updated += 1

        session.commit()
        print(
            f"updated_memberships={updated} total_memberships={len(memberships)} "
            f"user_id={user.id} email={user.email} role={target_role}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
