from __future__ import annotations

import json
import os
import re
from typing import Any

import requests
from pydantic import BaseModel, Field, ValidationError

from .prompts import build_structured_extraction_prompt
from .schemas import CitationType, FactDimension, NormativeStrength, PredicateValue, RelationType


class ExtractedSecondarySource(BaseModel):
    source_id: str
    title: str | None = None
    topic_tags: list[str] = Field(default_factory=list)


class ExtractedHolding(BaseModel):
    holding_text: str
    if_condition: list[PredicateValue] = Field(default_factory=list)
    then_consequence: list[PredicateValue] = Field(default_factory=list)
    normative_strength: NormativeStrength = NormativeStrength.binding_core
    normative_source: list[str] = Field(default_factory=list)
    fact_vector: list[FactDimension] = Field(default_factory=list)
    secondary_sources: list[ExtractedSecondarySource] = Field(default_factory=list)
    citations_supporting: list[str] = Field(default_factory=list)


class ExtractedIssue(BaseModel):
    normalized_form: str
    taxonomy: dict[str, str] = Field(default_factory=dict)
    required_fact_dimensions: list[str] = Field(default_factory=list)
    supporting_citations: list[str] = Field(default_factory=list)


class ExtractedRelation(BaseModel):
    source_holding_index: int | None = None
    target_holding_index: int | None = None
    source_holding_id: str | None = None
    target_holding_id: str | None = None
    relation_type: RelationType
    citation_type: CitationType = CitationType.controlling
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_span: dict[str, int] = Field(default_factory=dict)


INTERPRETIVE_EDGE_TYPES = {
    "EXTENDS_AMENDMENT",
    "NARROWS_AMENDMENT",
    "BROADENS_AMENDMENT",
    "APPLIES_AMENDMENT",
    "EXPLAINS_AMENDMENT",
    "CLARIFIES_DOCTRINE",
    "INVALIDATES_STATUTE_UNDER",
    "INVALIDATES_REGULATION_UNDER",
    "UPHOLDS_STATUTE_AGAINST",
    "REJECTS_CONSTITUTIONAL_CHALLENGE",
    "RECOGNIZES_RIGHT_UNDER",
    "LIMITS_AMENDMENT_SCOPE",
    "QUESTIONS_PRECEDENT_UNDER",
    "OVERRULES_PRECEDENT_UNDER",
    "INTERPRETS_STATUTE",
    "BROADENS_STATUTE",
    "NARROWS_STATUTE",
    "APPLIES_PLAIN_MEANING",
    "USES_LEGISLATIVE_HISTORY",
    "APPLIES_LENITY",
    "APPLIES_CONSTITUTIONAL_AVOIDANCE",
    "FINDS_STATUTE_AMBIGUOUS",
    "RESOLVES_STATUTORY_AMBIGUITY",
    "INVALIDATES_STATUTE",
    "SEVERS_PROVISION",
    "DISTINGUISHES_STATUTE",
    "EXTENDS_STATUTE",
    "REJECTS_EXPANSIVE_READING",
    "CONSTRUES_TO_AVOID_CONSTITUTIONAL_ISSUE",
}
INTERPRETIVE_AUTHORITY_TYPES = {
    "CONSTITUTION",
    "STATUTE",
    "REGULATION",
    "FEDERAL_RULE",
    "PRIOR_CASE",
}


class ExtractedInterpretiveEdge(BaseModel):
    source_case: str
    target_authority: str
    authority_type: str
    edge_type: str
    confidence: float = Field(ge=0.0, le=1.0)
    text_span: str


class ExtractionEnvelope(BaseModel):
    holdings: list[ExtractedHolding] = Field(default_factory=list)
    issues: list[ExtractedIssue] = Field(default_factory=list)
    relations: list[ExtractedRelation] = Field(default_factory=list)
    interpretive_edges: list[ExtractedInterpretiveEdge] = Field(default_factory=list)


class ExtractionValidationError(ValueError):
    pass


_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", re.IGNORECASE)


def _ollama_output_schema() -> dict[str, Any]:
    scalar_value = {"type": ["string", "number", "boolean", "null"]}
    predicate_item = {
        "type": "object",
        "properties": {
            "predicate": {"type": "string"},
            "value": scalar_value,
        },
        "required": ["predicate", "value"],
    }
    fact_item = {
        "type": "object",
        "properties": {
            "dimension": {"type": "string"},
            "value": scalar_value,
        },
        "required": ["dimension", "value"],
    }
    secondary_source_item = {
        "type": "object",
        "properties": {
            "source_id": {"type": "string"},
            "title": {"type": "string"},
            "topic_tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["source_id"],
    }
    holding_item = {
        "type": "object",
        "properties": {
            "holding_text": {"type": "string"},
            "if_condition": {"type": "array", "items": predicate_item},
            "then_consequence": {"type": "array", "items": predicate_item},
            "normative_strength": {
                "type": "string",
                "enum": ["binding_core", "binding_narrow", "persuasive", "dicta"],
            },
            "normative_source": {"type": "array", "items": {"type": "string"}},
            "fact_vector": {"type": "array", "items": fact_item},
            "secondary_sources": {"type": "array", "items": secondary_source_item},
            "citations_supporting": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "holding_text",
            "if_condition",
            "then_consequence",
            "normative_strength",
            "citations_supporting",
        ],
    }
    issue_item = {
        "type": "object",
        "properties": {
            "normalized_form": {"type": "string"},
            "taxonomy": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string"},
                    "subdomain": {"type": "string"},
                    "doctrine": {"type": "string"},
                    "rule_type": {"type": "string"},
                },
            },
            "required_fact_dimensions": {"type": "array", "items": {"type": "string"}},
            "supporting_citations": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["normalized_form", "taxonomy", "supporting_citations"],
    }
    relation_item = {
        "type": "object",
        "properties": {
            "source_holding_index": {"type": "integer"},
            "target_holding_index": {"type": "integer"},
            "source_holding_id": {"type": "string"},
            "target_holding_id": {"type": "string"},
            "relation_type": {
                "type": "string",
                "enum": [
                    "applies",
                    "clarifies",
                    "extends",
                    "distinguishes",
                    "limits",
                    "overrules",
                    "questions",
                ],
            },
            "citation_type": {
                "type": "string",
                "enum": ["controlling", "persuasive", "background"],
            },
            "confidence": {"type": "number"},
            "evidence_span": {
                "type": "object",
                "properties": {
                    "start_char": {"type": "integer"},
                    "end_char": {"type": "integer"},
                },
                "required": ["start_char", "end_char"],
            },
        },
        "required": ["relation_type", "citation_type", "confidence", "evidence_span"],
    }
    interpretive_item = {
        "type": "object",
        "properties": {
            "source_case": {"type": "string"},
            "target_authority": {"type": "string"},
            "authority_type": {"type": "string", "enum": sorted(INTERPRETIVE_AUTHORITY_TYPES)},
            "edge_type": {"type": "string", "enum": sorted(INTERPRETIVE_EDGE_TYPES)},
            "confidence": {"type": "number"},
            "text_span": {"type": "string"},
        },
        "required": ["source_case", "target_authority", "authority_type", "edge_type", "confidence", "text_span"],
    }
    return {
        "type": "object",
        "properties": {
            "holdings": {"type": "array", "items": holding_item},
            "issues": {"type": "array", "items": issue_item},
            "relations": {"type": "array", "items": relation_item},
            "interpretive_edges": {"type": "array", "items": interpretive_item},
            # Accept strict-prompt alias where only `edges` is returned.
            "edges": {"type": "array", "items": interpretive_item},
        },
        "required": ["holdings", "issues", "relations"],
    }


def _coerce_json_payload(content: str) -> Any:
    text = (content or "").strip()
    if not text:
        raise json.JSONDecodeError("Empty content", content or "", 0)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = _FENCED_JSON_RE.search(text)
    if match:
        candidate = match.group(1).strip()
        return json.loads(candidate)

    first_obj = text.find("{")
    last_obj = text.rfind("}")
    if first_obj != -1 and last_obj != -1 and last_obj > first_obj:
        candidate = text[first_obj : last_obj + 1]
        return json.loads(candidate)

    return json.loads(text)


def _coerce_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def _coerce_confidence(value: Any, fallback: float = 0.6) -> float:
    try:
        parsed = float(value)
    except Exception:
        return fallback
    return max(0.0, min(1.0, parsed))


def _sanitize_extraction_dict(data: dict[str, Any]) -> dict[str, Any]:
    payload = dict(data)
    if "interpretive_edges" not in payload and isinstance(payload.get("edges"), list):
        payload["interpretive_edges"] = payload.get("edges")

    for key in ("holdings", "issues", "relations", "interpretive_edges"):
        if key not in payload:
            payload[key] = []
        if not isinstance(payload[key], list):
            payload[key] = []

    sanitized_relations = []
    for relation in payload.get("relations", []):
        if not isinstance(relation, dict):
            continue
        item = dict(relation)
        item.setdefault("relation_type", "clarifies")
        item.setdefault("citation_type", "controlling")
        item["confidence"] = _coerce_confidence(item.get("confidence"), fallback=0.6)

        evidence = item.get("evidence_span")
        if not isinstance(evidence, dict):
            evidence = {}
        start_char = _coerce_int(evidence.get("start_char"), fallback=0)
        end_char = _coerce_int(evidence.get("end_char"), fallback=start_char)
        if end_char < start_char:
            end_char = start_char
        item["evidence_span"] = {"start_char": start_char, "end_char": end_char}
        sanitized_relations.append(item)
    payload["relations"] = sanitized_relations

    sanitized_interpretive = []
    for edge in payload.get("interpretive_edges", []):
        if not isinstance(edge, dict):
            continue
        item = dict(edge)
        source_case = str(item.get("source_case") or "").strip()
        target_authority = str(item.get("target_authority") or "").strip()
        authority_type = str(item.get("authority_type") or "").strip().upper()
        edge_type = str(item.get("edge_type") or "").strip().upper()
        text_span = re.sub(r"\s+", " ", str(item.get("text_span") or "")).strip()
        confidence = _coerce_confidence(item.get("confidence"), fallback=0.65)
        if not source_case or not target_authority:
            continue
        if authority_type not in INTERPRETIVE_AUTHORITY_TYPES:
            continue
        if edge_type not in INTERPRETIVE_EDGE_TYPES:
            continue
        if len(text_span) > 800:
            text_span = text_span[:800].rstrip()
        sanitized_interpretive.append(
            {
                "source_case": source_case,
                "target_authority": target_authority,
                "authority_type": authority_type,
                "edge_type": edge_type,
                "confidence": confidence,
                "text_span": text_span,
            }
        )
    payload["interpretive_edges"] = sanitized_interpretive
    return payload


def parse_extraction_json(content: str) -> ExtractionEnvelope:
    try:
        data = _coerce_json_payload(content)
    except json.JSONDecodeError as exc:
        raise ExtractionValidationError(f"Invalid JSON payload: {exc}") from exc

    if not isinstance(data, dict):
        raise ExtractionValidationError("Schema validation failed: top-level payload must be an object")
    data = _sanitize_extraction_dict(data)

    try:
        if hasattr(ExtractionEnvelope, "model_validate"):
            return ExtractionEnvelope.model_validate(data)  # type: ignore[attr-defined]
        return ExtractionEnvelope.parse_obj(data)
    except ValidationError as exc:
        raise ExtractionValidationError(f"Schema validation failed: {exc}") from exc


def _ollama_request_payload(model: str, prompt: str) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": "Return only valid JSON. No prose."},
            {"role": "user", "content": prompt},
        ],
        "format": _ollama_output_schema(),
        "stream": False,
        "options": {"temperature": 0},
    }


def extract_structures(
    opinion_text: str,
    resolved_citations: list[dict] | None = None,
    *,
    model: str | None = None,
    ollama_url: str | None = None,
    timeout: int | None = None,
    session: requests.Session | None = None,
) -> ExtractionEnvelope:
    model_name = model or os.getenv("ACQUITTIFY_INGESTION_MODEL", "qwen-acquittify-ingestion14b")
    endpoint = ollama_url or os.getenv("ACQUITTIFY_INGESTION_OLLAMA_URL", "http://localhost:11434/api/chat")
    request_timeout = timeout if timeout is not None else int(os.getenv("ACQUITTIFY_INGESTION_TIMEOUT", "120"))
    prompt = build_structured_extraction_prompt(opinion_text, resolved_citations)

    client = session or requests.Session()
    response = client.post(
        endpoint,
        json=_ollama_request_payload(model_name, prompt),
        timeout=max(1, int(request_timeout)),
    )
    response.raise_for_status()
    payload = response.json()

    content = ""
    if isinstance(payload, dict):
        message = payload.get("message")
        if isinstance(message, dict):
            content = str(message.get("content") or "")
    if not content:
        raise ExtractionValidationError("LLM response missing message.content")

    return parse_extraction_json(content)
