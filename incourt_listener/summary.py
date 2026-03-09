from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests


DEFAULT_LLM_URL = os.getenv("INCOURT_LLM_URL", "http://localhost:11434/api/chat")
DEFAULT_LLM_MODEL = os.getenv("INCOURT_LLM_MODEL", "acquittify-qwen")
DEFAULT_TEMPERATURE = float(os.getenv("INCOURT_LLM_TEMPERATURE", "0.2"))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_ts(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _clean_sentences(text: str) -> List[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    parts = re.split(r"(?<=[\.\!\?])\s+", text)
    cleaned: List[str] = []
    seen = set()
    for part in parts:
        sentence = part.strip()
        if len(sentence.split()) < 4:
            continue
        key = sentence.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(sentence)
    return cleaned


def _rule_based_summary(text: str, max_sentences: int, target_chars: int) -> str:
    sentences = _clean_sentences(text)
    if not sentences:
        return ""
    # Prefer the most recent sentences to keep it "real-time".
    selected = sentences[-max_sentences:]
    summary = " ".join(selected)
    if len(summary) > target_chars:
        summary = summary[:target_chars].rsplit(" ", 1)[0].strip()
        if summary and summary[-1] not in ".!?":
            summary += "…"
    return summary


def _call_llm(prompt: str, max_tokens: int) -> Optional[str]:
    url = os.getenv("INCOURT_SUMMARY_LLM_URL", DEFAULT_LLM_URL)
    model = os.getenv("INCOURT_SUMMARY_LLM_MODEL", DEFAULT_LLM_MODEL)
    temperature = float(os.getenv("INCOURT_SUMMARY_LLM_TEMPERATURE", str(DEFAULT_TEMPERATURE)))
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You summarize live courtroom audio. "
                    "Return concise bullet points with no verbatim quotes. "
                    "Use present tense and neutral tone."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    response = requests.post(url, json=payload, timeout=45)
    response.raise_for_status()
    content = response.json().get("message", {}).get("content", "")
    return content.strip() if content else None


def summarize_window(
    segments: List[Dict[str, object]],
    max_bullets: int = 4,
    target_chars: int = 600,
    use_llm: bool = True,
) -> Dict[str, object]:
    window_text = " ".join([str(seg.get("text", "")).strip() for seg in segments]).strip()
    anchors = [seg.get("segment_id") for seg in segments if seg.get("segment_id")]

    summary_text = ""
    source = "rule"
    if use_llm and window_text:
        prompt = (
            "Summarize the following courtroom audio window into 2-4 bullet points. "
            "No verbatim quotes, no legal advice.\n\n"
            f"TRANSCRIPT WINDOW:\n{window_text}"
        )
        try:
            llm = _call_llm(prompt, max_tokens=220)
        except Exception:
            llm = None
        if llm:
            summary_text = llm
            source = "llm"

    if not summary_text:
        summary_text = _rule_based_summary(window_text, max_sentences=max_bullets, target_chars=target_chars)

    return {
        "created_at": _utc_now_iso(),
        "summary": summary_text,
        "anchors": anchors,
        "source": source,
    }


def filter_segments_by_window(
    segments: List[Dict[str, object]],
    window_sec: int,
) -> List[Dict[str, object]]:
    if not segments or window_sec <= 0:
        return segments
    now = datetime.now(timezone.utc)
    filtered: List[Dict[str, object]] = []
    cutoff = now.timestamp() - window_sec
    for seg in segments:
        ts = seg.get("ts_end") or seg.get("ts_start") or ""
        parsed = _parse_ts(str(ts))
        if parsed and parsed.timestamp() >= cutoff:
            filtered.append(seg)
    return filtered if filtered else segments
