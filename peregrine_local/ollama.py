from __future__ import annotations

from typing import Any
import requests

from .config import OLLAMA_CHAT_URL, OLLAMA_EMBED_URL, MODEL_NAME, EMBED_MODEL


def embed_text(text: str, timeout: int = 60) -> list[float]:
    payload = {"model": EMBED_MODEL, "prompt": text}
    response = requests.post(OLLAMA_EMBED_URL, json=payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    embedding = data.get("embedding")
    if not embedding:
        raise RuntimeError("Ollama embeddings response missing 'embedding'.")
    return embedding


def chat(
    messages: list[dict[str, str]],
    model: str | None = None,
    temperature: float = 0.2,
    timeout: int = 120,
) -> str:
    payload: dict[str, Any] = {
        "model": model or MODEL_NAME,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }
    response = requests.post(OLLAMA_CHAT_URL, json=payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    message = data.get("message")
    if isinstance(message, dict) and message.get("content"):
        return message["content"]
    if "response" in data:
        return str(data["response"])
    raise RuntimeError("Ollama chat response missing content.")
