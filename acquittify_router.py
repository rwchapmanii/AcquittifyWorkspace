"""Routing-only module: classify a user question into the fixed taxonomy.

This module issues a local Ollama model call to produce JSON-only output.
It MUST NOT perform legal analysis or produce citations.
"""
from typing import Dict, List
import json
import requests


def classify_question(question: str, ollama_url: str, model: str) -> Dict:
    """Classify a free-text legal question using the local Ollama model.

    Returns a dict: {primary_area, secondary_areas, confidence}

    Constraints enforced in the prompt: no legal analysis, no citations, no
    explanations — JSON-only output is required. If mapping is unclear, the
    model should use "General Federal Criminal Law" as primary_area.
    """
    prompt = (
        "You are a classification assistant. DO NOT PROVIDE LEGAL ANALYSIS, "
        "EXPLANATIONS, OR CITATIONS. Output MUST be valid JSON and NOTHING ELSE.\n\n"
        "Required JSON schema: {\n"
        "  \"primary_area\": string,  // one of the controlled taxonomy labels\n"
        "  \"secondary_areas\": [string],\n"
        "  \"confidence\": number   // between 0 and 1\n"
        "}\n\n"
        "If the question does not clearly map, set primary_area to "
        "\"General Federal Criminal Law\".\n\n"
        "QUESTION:\n" + question + "\n\n"
        "Return JSON only."
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You only classify; no analysis."},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.0},
    }

    resp = requests.post(ollama_url, json=payload, timeout=30)
    resp.raise_for_status()
    text = resp.json().get("message", {}).get("content", "")

    # Attempt to parse JSON from the model output; be defensive.
    try:
        parsed = json.loads(text)
    except Exception:
        # As a safe fallback, return a default mapping
        return {
            "primary_area": "General Federal Criminal Law",
            "secondary_areas": [],
            "confidence": 0.0,
        }

    # Normalize fields
    primary = parsed.get("primary_area") or "General Federal Criminal Law"
    secondary = parsed.get("secondary_areas") or []
    try:
        confidence = float(parsed.get("confidence", 0.0))
    except Exception:
        confidence = 0.0

    return {"primary_area": primary, "secondary_areas": secondary, "confidence": confidence}
