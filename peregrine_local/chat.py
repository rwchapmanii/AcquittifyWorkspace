from __future__ import annotations

from typing import List

from .ollama import chat as ollama_chat
from .searcher import search


SYSTEM_PROMPT = (
    "You are Peregrine, an internal-only legal discovery assistant. "
    "Use only the provided context from the Obsidian vault. "
    "If the answer is not in the context, say you cannot find it."
)


def build_context(results: List[dict]) -> str:
    parts: list[str] = []
    for idx, item in enumerate(results, start=1):
        path = item.get("path", "")
        snippet = item.get("snippet", "")
        parts.append(f"[Doc {idx}] {path}\n{snippet}")
    return "\n\n".join(parts)


def answer(query: str, limit: int = 5) -> dict:
    results = search(query, limit=limit)
    context = build_context(results)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Context:\n" + context + "\n\n" + "Question:\n" + query
            ),
        },
    ]
    response = ollama_chat(messages)
    return {"answer": response, "sources": results}
