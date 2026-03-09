from __future__ import annotations

import os
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_ROOT = PROJECT_ROOT / "acquittify-data"
DEFAULT_WORKSPACE_ID = "default"


def sanitize_workspace_id(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    cleaned = re.sub(r"[^a-z0-9_-]+", "-", raw).strip("-_")
    return cleaned or DEFAULT_WORKSPACE_ID


def resolve_data_root(value: str | Path | None = None, create: bool = True) -> Path:
    raw = value or os.getenv("ACQUITTIFY_DATA_ROOT") or DEFAULT_DATA_ROOT
    root = Path(raw).expanduser().resolve()
    if create:
        root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_workspace_id(value: str | None = None) -> str:
    return sanitize_workspace_id(value or os.getenv("ACQUITTIFY_WORKSPACE_ID"))


def resolve_offline_mode(value: str | None = None) -> bool:
    raw = str(value if value is not None else os.getenv("ACQUITTIFY_OFFLINE_MODE", "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def workspace_root(
    *,
    data_root: str | Path | None = None,
    workspace_id: str | None = None,
    create: bool = True,
) -> Path:
    root = resolve_data_root(data_root, create=create)
    ws_id = resolve_workspace_id(workspace_id)
    ws_root = (root / "workspaces" / ws_id).resolve()
    if create:
        ws_root.mkdir(parents=True, exist_ok=True)
    return ws_root


def ensure_within_root(root: Path, target: str | Path) -> Path:
    abs_root = Path(root).expanduser().resolve()
    abs_target = Path(target).expanduser().resolve()
    if abs_target == abs_root or str(abs_target).startswith(str(abs_root) + os.sep):
        return abs_target
    raise ValueError(f"Path outside workspace boundary: {abs_target}")


def workspace_path(
    *parts: str,
    data_root: str | Path | None = None,
    workspace_id: str | None = None,
    create_parent: bool = False,
) -> Path:
    root = workspace_root(data_root=data_root, workspace_id=workspace_id, create=True)
    target = ensure_within_root(root, root.joinpath(*parts))
    if create_parent:
        target.parent.mkdir(parents=True, exist_ok=True)
    return target
