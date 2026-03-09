from __future__ import annotations

import re
from typing import Dict, List


ISSUE_PATTERNS = {
    "hearsay": [
        re.compile(r"\b(he|she|they|someone)\s+(said|told me|tells me|told us)\b", re.I),
        re.compile(r"\baccording to\b", re.I),
    ],
    "speculation": [
        re.compile(r"\b(i think|i guess|maybe|probably|could be)\b", re.I),
    ],
    "foundation": [
        re.compile(r"\b(know|familiar with|recognize)\b", re.I),
        re.compile(r"\b(can you identify)\b", re.I),
    ],
    "leading": [
        re.compile(r"\b(isn't it true|you did|you were|you saw)\b", re.I),
    ],
    "prior_bad_acts": [
        re.compile(r"\b(previously convicted|prior arrest|bad acts)\b", re.I),
    ],
}


ISSUE_ACTIONS = {
    "hearsay": "Objection: hearsay. Request exclusion or limiting instruction.",
    "speculation": "Objection: speculation. Ask witness to testify to personal knowledge.",
    "foundation": "Objection: lack of foundation. Request authentication or foundation.",
    "leading": "Objection: leading question.",
    "prior_bad_acts": "Objection: improper character evidence / prior bad acts.",
}


def detect_issues(text: str) -> List[Dict[str, object]]:
    if not text:
        return []
    hits: List[Dict[str, object]] = []
    for issue_type, patterns in ISSUE_PATTERNS.items():
        for pattern in patterns:
            if pattern.search(text):
                hits.append(
                    {
                        "issue_type": issue_type,
                        "confidence": 0.55,
                        "reason": pattern.pattern,
                        "suggested_action": ISSUE_ACTIONS.get(issue_type, ""),
                    }
                )
                break
    return hits
