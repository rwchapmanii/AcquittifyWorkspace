from __future__ import annotations

import re
from functools import lru_cache

INTENT_PATTERNS = {
    "Investigate Facts": [r"\bwhat happened\b", r"\btimeline\b", r"\bsummarize (the )?facts\b"],
    "Prepare for Motion": [r"\bsuppress\b", r"\bmotion\b", r"\brule 12\b", r"\brule 29\b"],
    "Prepare for Cross / Trial": [r"\bcross\b", r"\bimpeach\b", r"\binconsistenc(y|ies)\b"],
    "Prepare for Sentencing": [r"\bsentenc(ing|e)\b", r"\bmitigat(e|ion)\b"],
    "Prepare for Appeal": [r"\bappeal\b", r"\bstandard of review\b"],
    "Case Research": [r"\bfind cases\b", r"\bcase law\b", r"\bresearch\b"],
    "Summarize / Explain": [r"\bsummarize\b", r"\bexplain\b", r"\bplain[- ]english\b"],
    "Challenge / Stress-Test Theory": [r"\bweakness\b", r"\bwhat are we missing\b", r"\bgovernment's best\b"],
}

INTENT_EXPANSIONS = {
    "Prepare for Motion": ["suppression", "warrant", "probable cause", "exclusionary rule"],
    "Prepare for Cross / Trial": ["impeachment", "credibility", "prior inconsistent"],
    "Prepare for Sentencing": ["guidelines", "variance", "mitigation"],
    "Prepare for Appeal": ["standard of review", "harmless error", "preserved error"],
    "Case Research": ["holding", "precedent", "jurisdiction"],
    "Investigate Facts": ["timeline", "events", "witnesses"],
}


def classify_intent(question: str) -> str | None:
    q = (question or "").lower()
    for intent, patterns in INTENT_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, q):
                return intent
    return None


@lru_cache(maxsize=1024)
def expand_query(question: str, intent: str | None = None) -> str:
    base = (question or "").strip()
    if not base:
        return base
    expansions = []

    # Statute/rule hints
    if re.search(r"\b(\d+\s*U\.S\.C\.|\d+\s*usc)\b", base, re.IGNORECASE):
        expansions.append("statute")
    if re.search(r"\b(rule\s*\d+|fre\s*\d+|frcp\s*\d+)\b", base, re.IGNORECASE):
        expansions.append("rule")

    if intent and intent in INTENT_EXPANSIONS:
        expansions.extend(INTENT_EXPANSIONS[intent])

    if not expansions:
        return base

    return base + " | " + " ".join(sorted(set(expansions)))