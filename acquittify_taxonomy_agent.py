"""acquittify_taxonomy_agent.py

Second agent for Acquittify: Taxonomy-aware classification of legal questions.

This agent uses the local Ollama LLM to interpret legal questions and map them
to the taxonomy defined in acquittify_taxonomy.py. It is trained (via prompting)
to understand the taxonomy and provide structured classifications.

Exports:
- classify_question(question: str, ollama_url: str, model: str) -> Dict
"""

import json
import requests
from typing import Dict, List
from acquittify_taxonomy import TAXONOMY, TAXONOMY_SET, HIERARCHY


def classify_question(question: str, ollama_url: str, model: str) -> Dict:
    """Classify a legal question into taxonomy areas using the local LLM.

    Returns a dict with keys: primary_area, secondary_areas, confidence.
    Falls back to defaults if classification fails.
    """
    # Build a detailed prompt that includes the taxonomy
    taxonomy_str = "\n".join(f"- {code}" for code in TAXONOMY[:50])  # Limit to first 50 to avoid too long prompt
    if len(TAXONOMY) > 50:
        taxonomy_str += "\n... (and more codes)"

    prompt = f"""
You are a legal taxonomy expert for Federal Criminal Defense (FCD). Your task is to classify legal questions into the FCD taxonomy codes.

Available Taxonomy Codes (sample):
{taxonomy_str}

For the question: "{question}"

Respond ONLY with a JSON object in this exact format:
{{
  "primary_area": "Exact FCD code from taxonomy, e.g., FCD.ISS.SUPPRESSION.4A_SEARCH_SEIZURE",
  "secondary_areas": ["List", "of", "additional", "relevant", "codes"],
  "confidence": 0.0 to 1.0
}}

Do not include any other text, explanations, or legal analysis. Only the JSON.
"""

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1}  # Low temperature for consistency
    }

    try:
        response = requests.post(ollama_url, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        content = result.get("response", "").strip()

        # Parse JSON
        classification = json.loads(content)
        # Validate primary_area
        if classification.get("primary_area") not in TAXONOMY_SET:
            classification["primary_area"] = "General Federal Criminal Law"
        # Ensure secondary_areas is a list
        if not isinstance(classification.get("secondary_areas"), list):
            classification["secondary_areas"] = []
        # Ensure confidence is float
        classification["confidence"] = float(classification.get("confidence", 0.5))

        return classification

    except Exception as e:
        # Fallback
        return {
            "primary_area": "General Federal Criminal Law",
            "secondary_areas": [],
            "confidence": 0.0
        }


# Example usage (for testing)
if __name__ == "__main__":
    # Test with sample question
    q = "What are the rules for suppressing evidence from an illegal search?"
    result = classify_question(q, "http://localhost:11434/api/generate", "your-model-name")
    print(result)