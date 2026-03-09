#!/usr/bin/env python3
"""Sanity-check for the Electron desktop launcher paths."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

DEFAULT_PYTHON = Path("/Library/Frameworks/Python.framework/Versions/3.13/bin/python3")
FALLBACK_PYTHON = Path("/usr/bin/python3")


def resolve_existing_path(candidates: list[Path | None]) -> Path | None:
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate
    return None


def resolve_app_root() -> Path:
    return Path(os.environ.get("ACQUITTIFY_APP_ROOT", Path(__file__).resolve().parents[1]))


def resolve_python_path(app_root: Path) -> Path:
    return (
        resolve_existing_path(
            [
                Path(os.environ["ACQUITTIFY_PYTHON"]) if os.environ.get("ACQUITTIFY_PYTHON") else None,
                app_root / ".venv" / "bin" / "python",
                DEFAULT_PYTHON,
                Path("/opt/homebrew/bin/python3"),
                FALLBACK_PYTHON,
            ]
        )
        or FALLBACK_PYTHON
    )


def resolve_streamlit_app(app_root: Path) -> Path | None:
    return resolve_existing_path(
        [
            Path(os.environ["ACQUITTIFY_APP"]) if os.environ.get("ACQUITTIFY_APP") else None,
            app_root / "app.py",
        ]
    )


def main() -> int:
    app_root = resolve_app_root()
    python_path = resolve_python_path(app_root)
    streamlit_app = resolve_streamlit_app(app_root)

    print("Acquittify desktop launch check")
    print(f"APP_ROOT: {app_root}")
    print(f"PYTHON:   {python_path}")
    print(f"APP.PY:   {streamlit_app or 'NOT FOUND'}")

    if not streamlit_app:
        print("ERROR: app.py not found. Set ACQUITTIFY_APP or ACQUITTIFY_APP_ROOT.")
        return 2

    if not python_path.exists():
        print("ERROR: Python not found. Set ACQUITTIFY_PYTHON.")
        return 3

    try:
        result = subprocess.run(
            [str(python_path), "-c", "import streamlit; print(streamlit.__version__)"]
        )
    except OSError as exc:
        print(f"ERROR: Failed to execute Python: {exc}")
        return 4

    if result.returncode != 0:
        print("ERROR: Streamlit import failed. Install streamlit in the selected Python.")
        return 5

    print("OK: Streamlit is importable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
