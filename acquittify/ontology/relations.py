from __future__ import annotations

from dataclasses import dataclass
import re

from .schemas import RelationNode, RelationType, CitationType


_RELATION_MODIFIERS = {
    RelationType.applies: 1.0,
    RelationType.clarifies: 0.7,
    RelationType.extends: 0.8,
    RelationType.distinguishes: 0.6,
    RelationType.limits: 0.45,
    RelationType.overrules: 0.1,
    RelationType.questions: 0.35,
}

_HIGH_SIGNAL_PATTERNS: list[tuple[re.Pattern[str], RelationType, float]] = [
    (re.compile(r"\boverrul(?:e|ed|ing)\b", re.IGNORECASE), RelationType.overrules, 0.98),
    (re.compile(r"\blimit(?:s|ed|ing)?\b", re.IGNORECASE), RelationType.limits, 0.9),
    (re.compile(r"\bdistinguish(?:es|ed|ing)?\b", re.IGNORECASE), RelationType.distinguishes, 0.88),
    (re.compile(r"\bclarif(?:y|ies|ied)\b", re.IGNORECASE), RelationType.clarifies, 0.86),
    (re.compile(r"\bextend(?:s|ed|ing)\b", re.IGNORECASE), RelationType.extends, 0.86),
    (re.compile(r"\bapply(?:ing|ies|ied)?\b", re.IGNORECASE), RelationType.applies, 0.84),
    (re.compile(r"\bquestion(?:s|ed|ing)?\b", re.IGNORECASE), RelationType.questions, 0.8),
]


@dataclass(frozen=True)
class RelationBuildResult:
    relations: list[RelationNode]
    unresolved: list[dict]


def _holding_sequence(holding_id: str) -> int:
    match = re.search(r"\.H(\d+)$", holding_id)
    if not match:
        return 10_000
    return int(match.group(1))


def _holding_from_case_id(case_id: str, known_holding_ids: set[str]) -> str | None:
    case_id = (case_id or "").strip()
    if not case_id:
        return None
    parts = case_id.split(".")
    if len(parts) < 2:
        return None

    case_prefix = ".".join(parts[:-1])
    candidates = [hid for hid in known_holding_ids if hid.startswith(f"{case_prefix}.H")]
    if not candidates:
        return None
    return sorted(candidates, key=lambda hid: (_holding_sequence(hid), hid))[0]


def _span_center(evidence_span: dict) -> int | None:
    start = evidence_span.get("start_char")
    end = evidence_span.get("end_char")
    if isinstance(start, int) and isinstance(end, int) and end >= start:
        return (start + end) // 2
    return None


def _mention_distance(mention: dict, center: int | None) -> int:
    if center is None:
        start = mention.get("start_char")
        return int(start) if isinstance(start, int) else 10_000_000
    m_start = mention.get("start_char")
    m_end = mention.get("end_char")
    if not isinstance(m_start, int) or not isinstance(m_end, int):
        return 10_000_000
    if m_start <= center <= m_end:
        return 0
    if center < m_start:
        return m_start - center
    return center - m_end


def _role_rank(role: str | None) -> int:
    if role == "controlling":
        return 0
    if role == "persuasive":
        return 1
    if role == "background":
        return 2
    return 3


def _mentions_near_evidence(citation_mentions: list[dict], evidence_span: dict, window_chars: int = 260) -> list[dict]:
    start = evidence_span.get("start_char")
    end = evidence_span.get("end_char")
    if not isinstance(start, int) or not isinstance(end, int):
        return list(citation_mentions)

    left = max(0, start - window_chars)
    right = end + window_chars
    nearby: list[dict] = []
    for mention in citation_mentions:
        m_start = mention.get("start_char")
        m_end = mention.get("end_char")
        if not isinstance(m_start, int) or not isinstance(m_end, int):
            continue
        if m_end < left or m_start > right:
            continue
        nearby.append(mention)
    return nearby


def _infer_target_holding_id(
    evidence_span: dict,
    citation_mentions: list[dict],
    known_holding_ids: set[str],
) -> str | None:
    candidates = _mentions_near_evidence(citation_mentions, evidence_span)
    center = _span_center(evidence_span)

    ranked = sorted(
        candidates,
        key=lambda mention: (
            _role_rank(mention.get("role")),
            _mention_distance(mention, center),
            int(mention.get("start_char") or 10_000_000),
        ),
    )
    for mention in ranked:
        resolved_case_id = mention.get("resolved_case_id")
        if not isinstance(resolved_case_id, str):
            continue
        inferred = _holding_from_case_id(resolved_case_id, known_holding_ids)
        if inferred:
            return inferred
    return None


def _relation_id(source_holding_id: str, relation_type: RelationType, target_holding_id: str) -> str:
    return f"rel.{source_holding_id}__{relation_type.value}__{target_holding_id}"


def _parse_relation_type(raw: str | RelationType | None) -> RelationType:
    if isinstance(raw, RelationType):
        return raw
    if isinstance(raw, str):
        cleaned = raw.strip().lower()
        for relation_type in RelationType:
            if relation_type.value == cleaned:
                return relation_type
    return RelationType.clarifies


def _parse_citation_type(raw: str | CitationType | None) -> CitationType:
    if isinstance(raw, CitationType):
        return raw
    if isinstance(raw, str):
        cleaned = raw.strip().lower()
        for citation_type in CitationType:
            if citation_type.value == cleaned:
                return citation_type
    return CitationType.controlling


def _context_window(opinion_text: str, evidence_span: dict, window_chars: int = 200) -> str:
    start = evidence_span.get("start_char")
    end = evidence_span.get("end_char")
    if not isinstance(start, int) or not isinstance(end, int):
        return opinion_text[: min(1000, len(opinion_text))]
    left = max(0, start - window_chars)
    right = min(len(opinion_text), end + window_chars)
    return opinion_text[left:right]


def classify_relation(
    proposed_type: RelationType,
    opinion_text: str,
    evidence_span: dict,
    proposed_confidence: float,
) -> tuple[RelationType, float]:
    window = _context_window(opinion_text, evidence_span)
    for pattern, relation_type, confidence in _HIGH_SIGNAL_PATTERNS:
        if pattern.search(window):
            return relation_type, max(proposed_confidence, confidence)

    confidence = proposed_confidence if isinstance(proposed_confidence, (int, float)) else 0.6
    confidence = max(0.0, min(1.0, float(confidence)))
    return proposed_type, confidence


def _safe_quote(opinion_text: str, evidence_span: dict, max_words: int = 25) -> str:
    start = evidence_span.get("start_char")
    end = evidence_span.get("end_char")
    if isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(opinion_text):
        snippet = opinion_text[start:end]
    else:
        snippet = ""
    words = snippet.split()
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words])


def build_relation_nodes(
    extracted_relations: list,
    holding_ids: list[str],
    opinion_text: str,
    known_holding_ids: set[str] | None = None,
    citation_mentions: list[dict] | None = None,
) -> RelationBuildResult:
    relations: list[RelationNode] = []
    unresolved: list[dict] = []
    known_ids = set(holding_ids).union(known_holding_ids or set())
    mention_context = citation_mentions or []

    for idx, relation in enumerate(extracted_relations):
        source_idx = relation.source_holding_index
        target_idx = relation.target_holding_index
        source_holding_id = relation.source_holding_id if relation.source_holding_id in known_ids else None
        target_holding_id = relation.target_holding_id if relation.target_holding_id in known_ids else None

        if source_holding_id is None and isinstance(source_idx, int) and 0 <= source_idx < len(holding_ids):
            source_holding_id = holding_ids[source_idx]
        if target_holding_id is None and isinstance(target_idx, int) and 0 <= target_idx < len(holding_ids):
            target_holding_id = holding_ids[target_idx]
        if target_holding_id is None and mention_context:
            target_holding_id = _infer_target_holding_id(
                evidence_span=dict(relation.evidence_span or {}),
                citation_mentions=mention_context,
                known_holding_ids=known_ids,
            )

        if source_holding_id is None or target_holding_id is None:
            reason = "holding_index_out_of_range"
            if source_holding_id is None and relation.source_holding_id:
                reason = "source_holding_id_not_found"
            elif target_holding_id is None and relation.target_holding_id:
                reason = "target_holding_id_not_found"
            elif target_holding_id is None and mention_context:
                reason = "target_holding_inference_failed"
            unresolved.append(
                {
                    "type": "relation_unresolved",
                    "source_index": idx,
                    "reason": reason,
                    "source_holding_index": source_idx,
                    "target_holding_index": target_idx,
                    "source_holding_id": relation.source_holding_id,
                    "target_holding_id": relation.target_holding_id,
                }
            )
            continue

        proposed_type = _parse_relation_type(relation.relation_type)
        proposed_citation_type = _parse_citation_type(relation.citation_type)

        evidence_span = dict(relation.evidence_span or {})
        final_type, final_confidence = classify_relation(
            proposed_type=proposed_type,
            opinion_text=opinion_text,
            evidence_span=evidence_span,
            proposed_confidence=float(relation.confidence),
        )

        quote = _safe_quote(opinion_text, evidence_span)
        relation_id = _relation_id(source_holding_id, final_type, target_holding_id)

        node = RelationNode(
            relation_id=relation_id,
            source_holding_id=source_holding_id,
            target_holding_id=target_holding_id,
            relation_type=final_type,
            citation_type=proposed_citation_type,
            confidence=final_confidence,
            weight_modifier=_RELATION_MODIFIERS[final_type],
            evidence_span={
                "start_char": evidence_span.get("start_char"),
                "end_char": evidence_span.get("end_char"),
                "quote": quote,
            },
        )
        relations.append(node)

    dedup = {}
    for relation in relations:
        dedup[relation.relation_id] = relation

    merged = sorted(dedup.values(), key=lambda item: item.relation_id)
    return RelationBuildResult(relations=merged, unresolved=unresolved)
