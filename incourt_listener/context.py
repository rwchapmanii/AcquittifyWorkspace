from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List


CONTEXT_FILENAME = "case_context.json"

REQUIRED_FIELDS = [
    "case_caption",
    "jurisdiction",
    "proceeding_type",
    "charges",
    "contested_elements",
    "witnesses",
    "motions",
    "exhibits",
    "evidence_ruleset",
]


def default_context() -> Dict[str, object]:
    return {
        "case_caption": "",
        "jurisdiction": "",
        "proceeding_type": "",
        "charges": [],
        "contested_elements": [],
        "witnesses": [],
        "motions": [],
        "exhibits": [],
        "evidence_ruleset": "FRE",
    }


def load_case_context(case_root: Path) -> Dict[str, object]:
    path = case_root / CONTEXT_FILENAME
    if not path.exists():
        return default_context()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default_context()
    context = default_context()
    context.update(data or {})
    return context


def save_case_context(case_root: Path, data: Dict[str, object]) -> None:
    path = case_root / CONTEXT_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = default_context()
    payload.update(data or {})
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def validate_case_context(data: Dict[str, object]) -> List[str]:
    missing = []
    for field in REQUIRED_FIELDS:
        value = data.get(field)
        if value is None:
            missing.append(field)
            continue
        if isinstance(value, str) and not value.strip():
            missing.append(field)
            continue
        if isinstance(value, list) and len(value) == 0:
            missing.append(field)
            continue
    return missing
