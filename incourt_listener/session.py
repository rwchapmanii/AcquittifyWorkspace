from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4


SESSIONS_DIRNAME = "incourt_listener"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_session(case_root: Path, case_id: str, case_name: str) -> Dict[str, str]:
    session_id = f"session_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
    session_root = case_root / SESSIONS_DIRNAME / session_id
    session_root.mkdir(parents=True, exist_ok=True)
    meta = {
        "session_id": session_id,
        "case_id": case_id,
        "case_name": case_name,
        "started_at": _utc_now_iso(),
        "status": "active",
    }
    (session_root / "session.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return {"id": session_id, "path": str(session_root)}


def append_jsonl(path: Path, payload: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def append_transcript_text(path: Path, text: str) -> None:
    if not text:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text.rstrip() + "\n")


def load_recent_jsonl(path: Path, limit: int = 50) -> List[Dict]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    rows: List[Dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def mark_session_stopped(session_root: Path, status: str = "stopped") -> None:
    meta_path = session_root / "session.json"
    if not meta_path.exists():
        return
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    data["status"] = status
    data["ended_at"] = _utc_now_iso()
    meta_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def purge_session(session_root: Path) -> None:
    if session_root.exists():
        shutil.rmtree(session_root)


def session_paths(case_root: Path, session_id: str) -> Dict[str, Path]:
    base = case_root / SESSIONS_DIRNAME / session_id
    return {
        "root": base,
        "transcript": base / "transcript.jsonl",
        "transcript_text": base / "transcript.txt",
        "case_transcript_text": case_root / SESSIONS_DIRNAME / f"{session_id}.txt",
        "summary": base / "summary.jsonl",
        "summary_latest": base / "summary_latest.json",
        "metrics": base / "metrics.jsonl",
        "notes": base / "notes.jsonl",
        "alerts": base / "alerts.jsonl",
    }
