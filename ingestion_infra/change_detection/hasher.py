"""Hashing utilities for change detection."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict


def _normalize_payload(payload: Dict[Any, Any]) -> Dict[str, Any]:
    """Normalize payload keys for stable hashing."""
    cleaned: Dict[str, Any] = {}
    for key, value in payload.items():
        if key is None:
            continue
        cleaned[str(key)] = value
    return cleaned


def hash_payload(payload: Dict[str, Any]) -> str:
    """Return a stable SHA256 hash for a JSON payload."""
    normalized_payload = _normalize_payload(payload)
    normalized = json.dumps(normalized_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
