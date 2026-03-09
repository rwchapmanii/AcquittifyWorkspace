from __future__ import annotations

import os
import sys
from pathlib import Path

from streamlit import config as _config
from streamlit.runtime.credentials import check_credentials
from streamlit.web import bootstrap


def _resolve_app_root() -> Path:
    env_root = os.getenv("ACQUITTIFY_APP_ROOT")
    if env_root:
        return Path(env_root).expanduser()
    desktop_root = Path.home() / "Desktop" / "Acquittify"
    if desktop_root.exists():
        return desktop_root
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return bundle_root


def main() -> None:
    app_root = _resolve_app_root()
    app_path = app_root / "app.py"
    if not app_path.exists():
        raise SystemExit(f"Unable to locate app.py at {app_path}")

    os.chdir(app_root)
    app_root_str = str(app_root)
    if app_root_str not in sys.path:
        sys.path.insert(0, app_root_str)
    port = int(os.getenv("ACQUITTIFY_PORT", "8501"))
    flag_options = {
        "server.headless": False,
        "server.port": port,
    }
    main_script_path = str(app_path.resolve())
    _config._main_script_path = main_script_path
    bootstrap.load_config_options(flag_options=flag_options)
    check_credentials()
    bootstrap.run(main_script_path, False, [], flag_options)


if __name__ == "__main__":
    main()
