from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional


CASE_ROOT = Path(__file__).resolve().parent / "Casefiles"
CASE_META = "case.json"


@dataclass
class CasePaths:
    root: Path
    chats: Path
    documents: Path
    processed: Path
    chroma: Path
    archive: Path


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\-\s_]", "", name).strip().lower()
    slug = re.sub(r"[\s_]+", "_", slug)
    return slug or "case"


def get_case_paths(case_name: str) -> CasePaths:
    slug = slugify(case_name)
    root = CASE_ROOT / slug
    return CasePaths(
        root=root,
        chats=root / "chats",
        documents=root / "documents",
        processed=root / "processed",
        chroma=root / "chroma",
        archive=root / "archive",
    )


def get_case_paths_by_id(case_id: str) -> CasePaths:
    root = CASE_ROOT / case_id
    return CasePaths(
        root=root,
        chats=root / "chats",
        documents=root / "documents",
        processed=root / "processed",
        chroma=root / "chroma",
        archive=root / "archive",
    )


def ensure_case(case_name: str) -> CasePaths:
    paths = get_case_paths(case_name)
    paths.chats.mkdir(parents=True, exist_ok=True)
    paths.documents.mkdir(parents=True, exist_ok=True)
    paths.processed.mkdir(parents=True, exist_ok=True)
    paths.chroma.mkdir(parents=True, exist_ok=True)
    paths.archive.mkdir(parents=True, exist_ok=True)
    meta_path = paths.root / CASE_META
    if not meta_path.exists():
        meta_path.write_text(json.dumps({"name": case_name}, indent=2), encoding="utf-8")
    return paths


def ensure_case_by_id(
    case_id: str, case_name: str | None = None, dropbox_path: str | None = None
) -> CasePaths:
    paths = get_case_paths_by_id(case_id)
    paths.chats.mkdir(parents=True, exist_ok=True)
    paths.documents.mkdir(parents=True, exist_ok=True)
    paths.processed.mkdir(parents=True, exist_ok=True)
    paths.chroma.mkdir(parents=True, exist_ok=True)
    paths.archive.mkdir(parents=True, exist_ok=True)
    meta_path = paths.root / CASE_META
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            meta = {"name": case_name or case_id}
    else:
        meta = {"name": case_name or case_id}

    if case_name:
        meta["name"] = case_name
    if dropbox_path:
        meta["dropbox_path"] = dropbox_path

    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return paths


def list_cases() -> List[Dict[str, str]]:
    if not CASE_ROOT.exists():
        return []
    cases = []
    for p in CASE_ROOT.iterdir():
        if not p.is_dir():
            continue
        meta = p / CASE_META
        if not meta.exists():
            continue  # Only include directories with a case.json
        try:
            meta_data = json.loads(meta.read_text(encoding="utf-8"))
            name = meta_data.get("name", p.name)
            dropbox_path = meta_data.get("dropbox_path")
        except Exception:
            name = p.name
            dropbox_path = None
        cases.append({"id": p.name, "name": name, "dropbox_path": dropbox_path})
    return sorted(cases, key=lambda x: x["name"].lower())


def list_chat_files(paths: CasePaths) -> List[Path]:
    if not paths.chats.exists():
        return []
    return sorted(paths.chats.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def create_chat(paths: CasePaths, title: Optional[str] = None) -> Path:
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    chat_id = f"chat_{ts}"
    data = {
        "id": chat_id,
        "title": title or f"Chat {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "messages": [],
    }
    chat_path = paths.chats / f"{chat_id}.json"
    chat_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return chat_path


def load_chat(chat_path: Path) -> Dict:
    return json.loads(chat_path.read_text(encoding="utf-8"))


def save_chat(chat_path: Path, data: Dict) -> None:
    data["updated_at"] = _now_iso()
    chat_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def set_chat_title(chat_path: Path, title: str) -> None:
    data = load_chat(chat_path)
    data["title"] = title.strip() or data.get("title", "Untitled Chat")
    save_chat(chat_path, data)


def append_message(chat_path: Path, role: str, content: str) -> None:
    data = load_chat(chat_path)
    data.setdefault("messages", []).append({"role": role, "content": content})
    save_chat(chat_path, data)


def archive_chat(chat_path: Path, archive_dir: Path) -> Path:
    archive_dir.mkdir(parents=True, exist_ok=True)
    target = archive_dir / chat_path.name
    if target.exists():
        target = archive_dir / f"{chat_path.stem}_archived{chat_path.suffix}"
    chat_path.replace(target)
    return target


def delete_chat(chat_path: Path) -> None:
    if chat_path.exists():
        chat_path.unlink()


def export_chat_markdown(chat_path: Path) -> str:
    data = load_chat(chat_path)
    title = data.get("title", "Chat")
    lines = [f"# {title}", ""]
    for msg in data.get("messages", []):
        role = msg.get("role", "user").capitalize()
        content = msg.get("content", "")
        lines.append(f"## {role}\n")
        lines.append(content)
        lines.append("")
    return "\n".join(lines)


def list_documents(paths: CasePaths) -> List[Path]:
    if not paths.documents.exists():
        return []
    return sorted(paths.documents.glob("*"))


def list_all_cases() -> List[CasePaths]:
    if not CASE_ROOT.exists():
        return []
    return [get_case_paths_by_id(p.name) for p in CASE_ROOT.iterdir() if p.is_dir()]


def list_all_chats() -> List[Path]:
    all_chats: List[Path] = []
    for paths in list_all_cases():
        if paths.chats.exists():
            all_chats.extend(paths.chats.glob("*.json"))
    return sorted(all_chats, key=lambda p: p.stat().st_mtime, reverse=True)


def list_all_archived_chats() -> List[Path]:
    all_chats: List[Path] = []
    for paths in list_all_cases():
        if paths.archive.exists():
            all_chats.extend(paths.archive.glob("*.json"))
    return sorted(all_chats, key=lambda p: p.stat().st_mtime, reverse=True)
