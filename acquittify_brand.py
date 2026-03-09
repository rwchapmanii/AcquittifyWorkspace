from __future__ import annotations

import base64
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


def _resolve_logo_mark() -> Path:
    env_path = os.getenv("ACQUITTIFY_LOGO_PATH")
    if env_path:
        candidate = Path(env_path).expanduser()
        if candidate.exists():
            return candidate

    candidates = [
        PROJECT_ROOT / "assets" / "Black and white logo.png",
        PROJECT_ROOT / "assets" / "Logo Above Name.png",
        PROJECT_ROOT / "assets" / "app_icon.png",
        PROJECT_ROOT / "Acquittify Storage" / "Brading" / "Logo black.png",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    # Keep a stable default even when no image exists in the current environment.
    return candidates[0]


LOGO_MARK = _resolve_logo_mark()


def _b64(path: Path) -> str | None:
    if not path.exists():
        return None
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def render_brand_sidebar_bar(st, label: str = "Acquittify") -> None:
    logo_b64 = _b64(LOGO_MARK)
    if logo_b64:
        st.sidebar.markdown(
            f"""
            <div class="aq-brand-header">
                <img src="data:image/png;base64,{logo_b64}" class="aq-brand-logo-icon" alt="{label}" />
            </div>
            """,
            unsafe_allow_html=True,
        )
        return
    st.sidebar.markdown(
        f"<div class=\"aq-brand-bar\"><div class=\"aq-brand-wordmark\">{label}</div></div>",
        unsafe_allow_html=True,
    )


def render_brand_header(st, label: str = "Acquittify") -> None:
    logo_b64 = _b64(LOGO_MARK)
    if logo_b64:
        st.markdown(
            f"""
            <div class="aq-brand-header aq-brand-header--left">
                <img src="data:image/png;base64,{logo_b64}" class="aq-brand-logo" alt="{label}" />
                <div class="aq-brand-wordmark">{label}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return
    st.markdown(
        f"<div class=\"aq-brand-bar\"><div class=\"aq-brand-wordmark\">{label}</div></div>",
        unsafe_allow_html=True,
    )
