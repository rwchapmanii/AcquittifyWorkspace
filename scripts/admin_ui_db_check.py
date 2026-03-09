import sys

from admin_ui.db import get_conn


def main() -> int:
    try:
        with get_conn(write=False) as conn:
            conn.execute("SELECT 1").fetchone()
    except Exception as exc:
        print(f"admin_ui db check failed: {exc}")
        return 1
    print("admin_ui db check ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
