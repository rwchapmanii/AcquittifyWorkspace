from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import requests

from .issues import detect_issues
OLLAMA_URL = os.getenv("INCOURT_LLM_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.getenv("INCOURT_LLM_MODEL", "acquittify-qwen")
OLLAMA_TEMPERATURE = float(os.getenv("INCOURT_LLM_TEMPERATURE", "0.2"))

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_prompt(context: Dict[str, object], transcript_window: List[Dict[str, object]]) -> List[Dict[str, str]]:
    context_json = json.dumps(context, ensure_ascii=False)
    window_text = "\n".join([seg.get("text", "") for seg in transcript_window])
    anchors = [seg.get("segment_id") for seg in transcript_window if seg.get("segment_id")]
    system = (
        "You are In-Court Listener. Generate attorney-focused notes and issue alerts.\n"
        "Requirements:\n"
        "- Output strict JSON with keys: notes, alerts.\n"
        "- Each note/alert MUST include anchors from transcript.\n"
        "- If an anchor cannot be identified, do NOT output that item.\n"
        "- Do NOT invent citations. Only describe issues; citations are added later.\n"
        "Schema:\n"
        "{"
        "\"notes\": [{\"text\": str, \"anchors\": [str], \"confidence\": float}],"
        "\"alerts\": [{"
        "\"issue_type\": str,"
        "\"summary\": str,"
        "\"suggested_action\": str,"
        "\"confidence\": float,"
        "\"anchors\": [str]"
        "}]}."
    )
    user = (
        f"CASE CONTEXT:\n{context_json}\n\n"
        f"TRANSCRIPT WINDOW:\n{window_text}\n\n"
        f"AVAILABLE ANCHORS:\n{anchors}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _call_llm(messages: List[Dict[str, str]]) -> Optional[Dict[str, object]]:
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {"temperature": OLLAMA_TEMPERATURE},
    }
    response = requests.post(OLLAMA_URL, json=payload, timeout=120)
    response.raise_for_status()
    content = response.json().get("message", {}).get("content", "")
    try:
        return json.loads(content)
    except Exception:
        return None


def analyze_window(
    context: Dict[str, object],
    transcript_window: List[Dict[str, object]],
    use_llm: bool = True,
    chroma_dir: Optional[str] = None,
) -> Dict[str, object]:
    notes: List[Dict[str, object]] = []
    alerts: List[Dict[str, object]] = []

    window_text = " ".join([seg.get("text", "") for seg in transcript_window]).strip()
    anchors = [seg.get("segment_id") for seg in transcript_window if seg.get("segment_id")]

    if use_llm:
        try:
            llm_payload = _call_llm(_build_prompt(context, transcript_window))
            if llm_payload:
                notes = llm_payload.get("notes") or []
                alerts = llm_payload.get("alerts") or []
        except Exception:
            llm_payload = None

    if not alerts:
        for hit in detect_issues(window_text):
            alerts.append(
                {
                    "issue_type": hit["issue_type"],
                    "summary": f"Potential {hit['issue_type'].replace('_', ' ')} issue detected.",
                    "suggested_action": hit.get("suggested_action", ""),
                    "confidence": hit.get("confidence", 0.5),
                    "anchors": anchors,
                }
            )

    # Attach authorities
    seen = set()
    filtered_alerts: List[Dict[str, object]] = []
    for alert in alerts:
        issue_type = alert.get("issue_type") or "issue"
        if issue_type in seen:
            continue
        seen.add(issue_type)
        authorities = _safe_retrieve_authorities(
            issue_type=issue_type,
            snippet=window_text,
            jurisdiction=str(context.get("jurisdiction") or ""),
            chroma_dir=Path(chroma_dir) if chroma_dir else None,
        )
        alert["authorities"] = authorities
        alert["created_at"] = _utc_now_iso()
        filtered_alerts.append(alert)

    alerts = filtered_alerts

    for note in notes:
        note.setdefault("created_at", _utc_now_iso())

    return {"notes": notes, "alerts": alerts}


def _safe_retrieve_authorities(
    issue_type: str,
    snippet: str,
    jurisdiction: str,
    chroma_dir: Optional[Path],
) -> List[Dict[str, object]]:
    if os.getenv("INCOURT_DISABLE_RETRIEVAL", "").lower() in {"1", "true", "yes"}:
        return []
    try:
        from .retrieval import retrieve_authorities  # type: ignore
    except Exception as exc:
        logger.warning("In-court retrieval disabled (import error): %s", exc)
        return []
    try:
        return retrieve_authorities(
            issue_type=issue_type,
            snippet=snippet,
            jurisdiction=jurisdiction,
            chroma_dir=chroma_dir,
        )
    except Exception as exc:
        logger.warning("In-court retrieval failed: %s", exc)
        return []
