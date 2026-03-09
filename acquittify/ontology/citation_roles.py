from __future__ import annotations

from dataclasses import dataclass
import re

from .citation_extract import CitationMention
from .schemas import CitationRole


_CONTROL_PATTERNS: list[tuple[re.Pattern[str], float]] = [
    (re.compile(r"\bwe hold\b", re.IGNORECASE), 2.2),
    (re.compile(r"\bcontrolled by\b", re.IGNORECASE), 2.0),
    (re.compile(r"\bunder\b", re.IGNORECASE), 1.4),
    (re.compile(r"\bgoverned by\b", re.IGNORECASE), 1.8),
    (re.compile(r"\brequire[sd]?\b", re.IGNORECASE), 1.0),
    (re.compile(r"\bmandate[sd]?\b", re.IGNORECASE), 1.0),
]

_PERSUASIVE_PATTERNS: list[tuple[re.Pattern[str], float]] = [
    (re.compile(r"\bpersuasive\b", re.IGNORECASE), 2.0),
    (re.compile(r"\bdeclin(?:e|ed|ing) to follow\b", re.IGNORECASE), 2.1),
    (re.compile(r"\bnot binding\b", re.IGNORECASE), 1.7),
]

_BACKGROUND_PATTERNS: list[tuple[re.Pattern[str], float]] = [
    (re.compile(r"\bsee also\b", re.IGNORECASE), 2.1),
    (re.compile(r"\bsee generally\b", re.IGNORECASE), 2.1),
    (re.compile(r"\bfor example\b", re.IGNORECASE), 1.2),
    (re.compile(r"\be\.g\.\b", re.IGNORECASE), 1.2),
    (re.compile(r"\bcf\.\b", re.IGNORECASE), 1.4),
]


@dataclass(frozen=True)
class CitationRoleAssignment:
    mention: CitationMention
    role: CitationRole
    confidence: float
    evidence_window: str


def _window(text: str, start_char: int, end_char: int, window_chars: int) -> str:
    left = max(0, start_char - window_chars)
    right = min(len(text), end_char + window_chars)
    return text[left:right]


def _score_patterns(window_text: str, patterns: list[tuple[re.Pattern[str], float]]) -> float:
    score = 0.0
    for pattern, weight in patterns:
        if pattern.search(window_text):
            score += weight
    return score


def _confidence(score: float) -> float:
    if score <= 0:
        return 0.34
    return min(0.99, 0.45 + (score * 0.14))


def classify_citation_roles(
    opinion_text: str,
    mentions: list[CitationMention],
    window_chars: int = 180,
) -> list[CitationRoleAssignment]:
    assignments: list[CitationRoleAssignment] = []
    for mention in mentions:
        context_window = _window(opinion_text, mention.start_char, mention.end_char, window_chars)

        scores = {
            CitationRole.controlling: _score_patterns(context_window, _CONTROL_PATTERNS),
            CitationRole.persuasive: _score_patterns(context_window, _PERSUASIVE_PATTERNS),
            CitationRole.background: _score_patterns(context_window, _BACKGROUND_PATTERNS),
        }

        best_role = max(scores, key=scores.get)
        best_score = scores[best_role]

        if best_score == 0.0:
            # Absent explicit cues, treat citations as persuasive by default.
            best_role = CitationRole.persuasive

        assignments.append(
            CitationRoleAssignment(
                mention=mention,
                role=best_role,
                confidence=_confidence(best_score),
                evidence_window=context_window,
            )
        )

    return assignments
