import argparse
import secrets

from .auth import _hash_password
from .db import get_conn


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("username")
    parser.add_argument("password")
    parser.add_argument("--role", choices=["admin_reviewer", "read_only"], default="read_only")
    args = parser.parse_args()

    salt = secrets.token_hex(16)
    digest = _hash_password(args.password, salt)
    stored = f"{salt}${digest}"

    with get_conn(write=True) as conn:
        conn.execute(
            """
            INSERT INTO derived.admin_user (username, password_hash, role)
            VALUES (%s, %s, %s)
            ON CONFLICT (username) DO UPDATE SET
                password_hash = EXCLUDED.password_hash,
                role = EXCLUDED.role,
                updated_at = NOW()
            """,
            (args.username, stored, args.role),
        )
        conn.commit()


if __name__ == "__main__":
    main()
