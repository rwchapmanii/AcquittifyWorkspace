from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha1
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.models.document import Document
from app.db.models.document_entity import DocumentEntity
from app.db.models.entity import Entity
from app.db.models.exhibit import Exhibit

_MAX_LABEL_LEN = 88

NODE_COLORS = {
    "document": "#2563eb",
    "person": "#16a34a",
    "organization": "#0ea5e9",
    "case": "#1d4ed8",
    "court": "#0ea5e9",
    "event": "#f59e0b",
    "statement": "#dc2626",
    "knowledge": "#7c3aed",
    "evidence": "#db2777",
    "exhibit": "#ea580c",
    "document_type": "#4f46e5",
    "priority": "#9333ea",
    "taxonomy": "#ca8a04",
    "topic": "#4b5563",
    "unknown": "#6b7280",
}


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return slug.strip("-") or "value"


def _shorten(value: str | None, *, max_len: int = _MAX_LABEL_LEN) -> str:
    if not value:
        return ""
    clean = " ".join(str(value).split())
    if len(clean) <= max_len:
        return clean
    return f"{clean[: max_len - 1]}…"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _normalize_name(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip().lower()


def _extract_doc_type(pass1: dict[str, Any], pass2: dict[str, Any]) -> str | None:
    candidate = pass1.get("document_type")
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip()
    doc_type = _as_dict(pass1.get("doc_type"))
    category = doc_type.get("category")
    if isinstance(category, str) and category.strip():
        return category.strip()
    subtype = pass2.get("doc_subtype")
    if isinstance(subtype, str) and subtype.strip():
        return subtype.strip()
    return None


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    clean = " ".join(str(value).split()).strip()
    return clean or None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _compact_values(values: list[Any], *, limit: int = 8) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = _as_str(raw)
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(value)
        if len(cleaned) >= limit:
            break
    return cleaned


def _extract_document_date(
    *, pass1: dict[str, Any], ingested_at: datetime | None
) -> str | None:
    time_meta = _as_dict(pass1.get("time"))
    candidates = [
        pass1.get("document_date"),
        time_meta.get("sent_at"),
        time_meta.get("system_created_at"),
        time_meta.get("system_modified_at"),
    ]
    for candidate in candidates:
        text_value = _as_str(candidate)
        if not text_value:
            continue
        match = re.search(r"\d{4}-\d{2}-\d{2}", text_value)
        if match:
            return match.group(0)
        return text_value[:10]
    if isinstance(ingested_at, datetime):
        return ingested_at.date().isoformat()
    return None


def _to_standard_segment(value: str | None, *, fallback: str, max_len: int = 42) -> str:
    if not value:
        return fallback
    segment = re.sub(r"[^A-Za-z0-9]+", "_", value.upper()).strip("_")
    segment = re.sub(r"_+", "_", segment)
    if not segment:
        return fallback
    return segment[:max_len]


def _build_document_node_names(
    *,
    document_uuid: str,
    original_filename: str | None,
    pass1: dict[str, Any],
    pass2: dict[str, Any],
    ingested_at: datetime | None,
) -> tuple[str, str]:
    doc_identity = _as_dict(pass1.get("doc_identity"))
    doc_type = _as_str(_extract_doc_type(pass1, pass2)) or "Document"
    title = (
        _as_str(doc_identity.get("doc_title"))
        or _as_str(doc_identity.get("email_subject"))
        or _as_str(original_filename)
        or f"Document {document_uuid[:8]}"
    )
    doc_date = _extract_document_date(pass1=pass1, ingested_at=ingested_at) or "Undated"

    display_name = _shorten(f"{doc_date} | {doc_type} | {title}", max_len=118)
    node_name_standard = (
        f"DOC::"
        f"{_to_standard_segment(doc_date, fallback='UNDATED', max_len=24)}::"
        f"{_to_standard_segment(doc_type, fallback='DOCUMENT', max_len=24)}::"
        f"{_to_standard_segment(title, fallback=f'DOC_{document_uuid[:8]}', max_len=56)}"
    )
    return display_name, node_name_standard


def _build_document_summary(
    *,
    original_filename: str | None,
    pass1: dict[str, Any],
    pass2: dict[str, Any],
    pass4: dict[str, Any],
) -> str:
    doc_identity = _as_dict(pass1.get("doc_identity"))
    doc_title = _as_str(doc_identity.get("doc_title")) or _as_str(doc_identity.get("email_subject"))
    relevance = _as_str(pass1.get("relevance"))
    proponent = _as_str(pass1.get("proponent"))
    priority = _as_str(pass4.get("priority_code"))
    hot_doc = bool(pass4.get("hot_doc_candidate"))
    event_summaries = _compact_values(
        [_as_dict(item).get("summary") for item in _as_list(pass2.get("events"))], limit=2
    )

    segments: list[str] = []
    if doc_title:
        segments.append(doc_title)
    if event_summaries:
        segments.extend(event_summaries)
    if relevance:
        segments.append(f"Relevance {relevance}")
    if proponent:
        segments.append(f"Proponent {proponent}")
    if priority:
        segments.append(f"Priority {priority.upper()}")
    if hot_doc:
        segments.append("Hot document candidate")
    if not segments:
        segments.append(_as_str(original_filename) or "Document in casefile")
    return _shorten(" | ".join(segments), max_len=240)


def _collect_relation_token_weights(
    *, pass1: dict[str, Any], pass2: dict[str, Any], doc_type: str | None
) -> dict[str, int]:
    weights: dict[str, int] = {}

    def _add_token(prefix: str, value: Any, weight: int) -> None:
        normalized = _normalize_name(_as_str(value))
        if not normalized:
            return
        token = f"{prefix}:{normalized}"
        current = weights.get(token, 0)
        if weight > current:
            weights[token] = weight

    for witness in _as_list(pass1.get("witnesses")):
        _add_token("witness", witness, 5)

    _add_token("proponent", pass1.get("proponent"), 4)

    raw_entities = _as_dict(pass1.get("entities_raw"))
    for person in _as_list(raw_entities.get("people_mentioned")):
        _add_token("person", person, 3)
    for org in _as_list(raw_entities.get("orgs_mentioned")):
        _add_token("org", org, 3)

    for enriched in _as_list(pass2.get("entities_enriched")):
        _add_token("entity", _as_dict(enriched).get("name"), 2)

    _add_token("doctype", doc_type, 1)
    return weights


def _build_document_frontmatter_distilled(
    *,
    row: dict[str, Any],
    pass1: dict[str, Any],
    pass2: dict[str, Any],
    pass4: dict[str, Any],
    doc_type: str | None,
    node_display_name: str,
    node_name_standard: str,
    summary: str,
    related_document_names: list[str],
    related_document_ids: list[str],
) -> dict[str, Any]:
    doc_identity = _as_dict(pass1.get("doc_identity"))
    raw_entities = _as_dict(pass1.get("entities_raw"))
    trial_signals = _as_dict(pass2.get("generic_trial_signals"))
    privilege = _as_dict(pass2.get("privilege_sensitivity"))
    exhibit_candidate = _as_dict(pass4.get("exhibit_candidate"))

    witnesses = _compact_values(_as_list(pass1.get("witnesses")), limit=10)
    key_people = _compact_values(
        _as_list(raw_entities.get("people_mentioned"))
        + [_as_dict(item).get("name") for item in _as_list(pass2.get("entities_enriched"))],
        limit=12,
    )
    key_orgs = _compact_values(_as_list(raw_entities.get("orgs_mentioned")), limit=10)
    event_summaries = _compact_values(
        [_as_dict(item).get("summary") for item in _as_list(pass2.get("events"))], limit=4
    )
    statement_highlights = _compact_values(
        [_as_dict(item).get("text_span_ref") for item in _as_list(pass2.get("statements"))],
        limit=4,
    )
    knowledge_signals = _compact_values(
        [
            f"{_as_str(_as_dict(item).get('type')) or 'signal'}: {_as_str(_as_dict(item).get('about')) or ''}".strip()
            for item in _as_list(pass2.get("knowledge_signals"))
        ],
        limit=5,
    )
    pii_flags = _compact_values(_as_list(privilege.get("pii_flags")), limit=8)
    if bool(privilege.get("attorney_involved")):
        pii_flags = _compact_values(["Attorney involved", *pii_flags], limit=8)

    return {
        "node_name_standard": node_name_standard,
        "display_name": node_display_name,
        "document_title": (
            _as_str(doc_identity.get("doc_title"))
            or _as_str(doc_identity.get("email_subject"))
            or _as_str(row.get("original_filename"))
            or node_display_name
        ),
        "document_type": _as_str(doc_type) or "Document",
        "document_date": _extract_document_date(
            pass1=pass1, ingested_at=row.get("ingested_at")
        ),
        "summary": summary,
        "proponent": _as_str(pass1.get("proponent")),
        "relevance": _as_str(pass1.get("relevance")),
        "witnesses": witnesses,
        "key_people": key_people,
        "key_organizations": key_orgs,
        "related_documents": related_document_names,
        "related_document_ids": related_document_ids,
        "event_summaries": event_summaries,
        "statement_highlights": statement_highlights,
        "knowledge_signals": knowledge_signals,
        "similarity_hooks": _compact_values(_as_list(pass4.get("similarity_hooks")), limit=6),
        "priority_code": _as_str(pass4.get("priority_code")),
        "priority_rationale": _compact_values(_as_list(pass4.get("priority_rationale")), limit=6),
        "hot_doc_candidate": bool(pass4.get("hot_doc_candidate")),
        "hot_doc_confidence": _as_float(pass4.get("hot_doc_confidence")),
        "exhibit_candidate": bool(exhibit_candidate.get("is_candidate")),
        "exhibit_purposes": _compact_values(_as_list(exhibit_candidate.get("purposes")), limit=6),
        "likely_objection_hints": _compact_values(
            _as_list(exhibit_candidate.get("likely_objection_hints")), limit=6
        ),
        "defense_signals": {
            "trial_relevance_hint": _as_float(trial_signals.get("trial_relevance_hint")),
            "defense_value_likelihood": _as_float(
                trial_signals.get("defense_value_likelihood")
            ),
            "govt_reliance_likelihood": _as_float(
                trial_signals.get("govt_reliance_likelihood")
            ),
            "redundancy_hint": _as_float(trial_signals.get("redundancy_hint")),
            "jury_readability_hint": _as_float(
                trial_signals.get("jury_readability_hint")
            ),
        },
        "privilege_signals": {
            "attorney_involved": bool(privilege.get("attorney_involved")),
            "attorney_involved_confidence": _as_float(
                privilege.get("attorney_involved_confidence")
            ),
            "legal_advice_likelihood": _as_float(
                privilege.get("legal_advice_likelihood")
            ),
            "work_product_likelihood": _as_float(
                privilege.get("work_product_likelihood")
            ),
            "pii_flags": pii_flags,
        },
    }


@dataclass
class _DocumentGraphProfile:
    row: dict[str, Any]
    document_uuid: str
    pass1: dict[str, Any]
    pass2: dict[str, Any]
    pass4: dict[str, Any]
    doc_type: str | None
    node_display_name: str
    node_name_standard: str
    summary: str
    token_weights: dict[str, int]
    related_document_ids: list[str] = field(default_factory=list)
    related_document_names: list[str] = field(default_factory=list)
    frontmatter_distilled: dict[str, Any] = field(default_factory=dict)


def _entity_kind_from_text(value: str | None, fallback: str = "person") -> str:
    text_value = (value or "").strip().lower()
    if text_value in {"org", "organization", "company"}:
        return "organization"
    if text_value in {"person", "individual", "witness"}:
        return "person"
    return fallback


def _case_domain_from_type(case_type: str | None) -> str:
    text_value = (case_type or "").strip().lower()
    if "criminal" in text_value or "quasi" in text_value:
        return "criminal"
    return "civil"


def _extract_primary_citation(frontmatter: dict[str, Any]) -> str:
    sources = _as_dict(frontmatter.get("sources"))
    primary = str(sources.get("primary_citation") or "").strip()
    if primary:
        return primary
    citations = _as_list(frontmatter.get("citations_in_text"))
    if citations:
        return str(citations[0] or "").strip()
    return ""


def _edge_key(*, source: str, target: str, edge_type: str, label: str) -> str:
    digest = sha1(f"{source}|{target}|{edge_type}|{label}".encode("utf-8")).hexdigest()[
        :12
    ]
    return f"edge:{digest}"


@dataclass
class _GraphBuilder:
    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    edges: dict[tuple[str, str, str, str], dict[str, Any]] = field(default_factory=dict)
    degrees: defaultdict[str, int] = field(default_factory=lambda: defaultdict(int))
    actor_index: dict[str, str] = field(default_factory=dict)
    actor_counter: int = 0

    def ensure_node(
        self,
        *,
        node_id: str,
        label: str,
        node_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        normalized_type = node_type if node_type in NODE_COLORS else "unknown"
        node = self.nodes.get(node_id)
        if node is None:
            node = {
                "id": node_id,
                "label": _shorten(label) or node_id,
                "type": normalized_type,
                "group": normalized_type,
                "color": NODE_COLORS.get(normalized_type, NODE_COLORS["unknown"]),
                "value": 10,
                "metadata": {},
            }
            self.nodes[node_id] = node
        if metadata:
            node["metadata"].update(
                {key: value for key, value in metadata.items() if value is not None}
            )
        return node_id

    def ensure_actor(
        self,
        *,
        name: str | None,
        node_type: str = "person",
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        clean = _shorten(name, max_len=120).strip()
        if not clean:
            return None
        key = _normalize_name(clean)
        if key in self.actor_index:
            node_id = self.actor_index[key]
            if metadata:
                self.nodes[node_id]["metadata"].update(metadata)
            return node_id
        self.actor_counter += 1
        node_id = f"actor:{_safe_slug(clean)}:{self.actor_counter}"
        self.ensure_node(
            node_id=node_id,
            label=clean,
            node_type=node_type,
            metadata={"name": clean, **(metadata or {})},
        )
        self.actor_index[key] = node_id
        return node_id

    def register_entity_name(self, *, name: str, node_id: str) -> None:
        normalized = _normalize_name(name)
        if normalized and normalized not in self.actor_index:
            self.actor_index[normalized] = node_id

    def add_edge(
        self,
        *,
        source: str,
        target: str,
        edge_type: str,
        label: str | None = None,
        metadata: dict[str, Any] | None = None,
        weight: float = 1.0,
    ) -> None:
        if source == target:
            return
        resolved_label = _shorten(label or edge_type, max_len=56) or edge_type
        key = (source, target, edge_type, resolved_label)
        existing = self.edges.get(key)
        if existing is None:
            edge = {
                "id": _edge_key(
                    source=source, target=target, edge_type=edge_type, label=resolved_label
                ),
                "from": source,
                "to": target,
                "type": edge_type,
                "label": resolved_label,
                "weight": max(0.1, float(weight)),
                "metadata": dict(metadata or {}),
                "arrows": "to",
            }
            self.edges[key] = edge
        else:
            existing["weight"] = float(existing["weight"]) + max(0.1, float(weight))
            if metadata:
                existing["metadata"].update(metadata)
        self.degrees[source] += 1
        self.degrees[target] += 1

    def finalize(self) -> dict[str, Any]:
        for node_id, node in self.nodes.items():
            degree = self.degrees[node_id]
            node["value"] = max(10, min(52, 10 + degree * 2))
            node["title"] = _shorten(node.get("metadata", {}).get("summary"), max_len=180) or ""
        nodes = sorted(self.nodes.values(), key=lambda row: (row["type"], row["label"]))
        edges = sorted(
            self.edges.values(),
            key=lambda row: (row["type"], row["from"], row["to"], row["label"]),
        )
        node_counts: defaultdict[str, int] = defaultdict(int)
        edge_counts: defaultdict[str, int] = defaultdict(int)
        for node in nodes:
            node_counts[node["type"]] += 1
        for edge in edges:
            edge_counts[edge["type"]] += 1
        return {
            "nodes": nodes,
            "edges": edges,
            "meta": {
                "node_type_counts": dict(sorted(node_counts.items())),
                "edge_type_counts": dict(sorted(edge_counts.items())),
                "node_count": len(nodes),
                "edge_count": len(edges),
            },
        }


def _add_topic(builder: _GraphBuilder, *, label: str, topic_kind: str = "topic") -> str:
    node_id = f"{topic_kind}:{_safe_slug(label)}"
    builder.ensure_node(
        node_id=node_id,
        label=label,
        node_type=topic_kind if topic_kind in NODE_COLORS else "topic",
        metadata={"name": label},
    )
    return node_id


def _add_document_metadata_topics(
    *,
    builder: _GraphBuilder,
    document_node_id: str,
    pass1: dict[str, Any],
    pass2: dict[str, Any],
    pass4: dict[str, Any],
) -> None:
    doc_type = _extract_doc_type(pass1, pass2)
    if doc_type:
        doc_type_node = _add_topic(builder, label=doc_type, topic_kind="document_type")
        builder.add_edge(
            source=document_node_id,
            target=doc_type_node,
            edge_type="classified_as",
            label="classified as",
        )

    priority_code = pass4.get("priority_code")
    if isinstance(priority_code, str) and priority_code.strip():
        priority_node = _add_topic(
            builder, label=priority_code.strip().upper(), topic_kind="priority"
        )
        builder.add_edge(
            source=document_node_id,
            target=priority_node,
            edge_type="priority",
            label="priority",
        )

    if bool(pass4.get("hot_doc_candidate")):
        hot_node = _add_topic(builder, label="Hot Document", topic_kind="topic")
        builder.add_edge(
            source=document_node_id,
            target=hot_node,
            edge_type="hot_doc_candidate",
            label="hot doc",
        )

    exhibit_candidate = _as_dict(pass4.get("exhibit_candidate"))
    if exhibit_candidate.get("is_candidate"):
        exhibit_candidate_node = _add_topic(
            builder, label="Exhibit Candidate", topic_kind="topic"
        )
        builder.add_edge(
            source=document_node_id,
            target=exhibit_candidate_node,
            edge_type="exhibit_candidate",
            label="exhibit candidate",
        )
        for purpose in _as_list(exhibit_candidate.get("purposes")):
            if isinstance(purpose, str) and purpose.strip():
                purpose_node = _add_topic(builder, label=purpose.strip(), topic_kind="topic")
                builder.add_edge(
                    source=exhibit_candidate_node,
                    target=purpose_node,
                    edge_type="exhibit_purpose",
                    label="purpose",
                )


def _add_authorship_links(
    *,
    builder: _GraphBuilder,
    document_node_id: str,
    pass1: dict[str, Any],
) -> None:
    authorship = _as_dict(pass1.get("authorship_transmission"))
    sender = authorship.get("sender")
    sender_node = builder.ensure_actor(
        name=sender, node_type="person", metadata={"origin": "authorship.sender"}
    )
    if sender_node:
        builder.add_edge(
            source=document_node_id,
            target=sender_node,
            edge_type="sender",
            label="sender",
        )

    for author in _as_list(authorship.get("author_names")):
        if not isinstance(author, str):
            continue
        author_node = builder.ensure_actor(
            name=author, node_type="person", metadata={"origin": "authorship.author"}
        )
        if author_node:
            builder.add_edge(
                source=document_node_id,
                target=author_node,
                edge_type="author",
                label="author",
            )

    for recipients_key, edge_type in (
        ("recipients_to", "recipient_to"),
        ("recipients_cc", "recipient_cc"),
        ("recipients_bcc", "recipient_bcc"),
    ):
        for recipient in _as_list(authorship.get(recipients_key)):
            if not isinstance(recipient, str):
                continue
            recipient_node = builder.ensure_actor(
                name=recipient,
                node_type="person",
                metadata={"origin": f"authorship.{recipients_key}"},
            )
            if recipient_node:
                builder.add_edge(
                    source=document_node_id,
                    target=recipient_node,
                    edge_type=edge_type,
                    label=edge_type.replace("_", " "),
                )

    for organization in _as_list(authorship.get("organizations")):
        if not isinstance(organization, str):
            continue
        org_node = builder.ensure_actor(
            name=organization,
            node_type="organization",
            metadata={"origin": "authorship.organization"},
        )
        if org_node:
            builder.add_edge(
                source=document_node_id,
                target=org_node,
                edge_type="organization",
                label="organization",
            )


def _add_pass_entities(
    *,
    builder: _GraphBuilder,
    document_node_id: str,
    pass1: dict[str, Any],
    pass2: dict[str, Any],
) -> None:
    entities_raw = _as_dict(pass1.get("entities_raw"))
    for person_name in _as_list(entities_raw.get("people_mentioned")):
        if not isinstance(person_name, str):
            continue
        person_node = builder.ensure_actor(
            name=person_name, node_type="person", metadata={"origin": "pass1.people"}
        )
        if person_node:
            builder.add_edge(
                source=document_node_id,
                target=person_node,
                edge_type="mentions_person",
                label="mentions",
            )

    for org_name in _as_list(entities_raw.get("orgs_mentioned")):
        if not isinstance(org_name, str):
            continue
        org_node = builder.ensure_actor(
            name=org_name, node_type="organization", metadata={"origin": "pass1.orgs"}
        )
        if org_node:
            builder.add_edge(
                source=document_node_id,
                target=org_node,
                edge_type="mentions_org",
                label="mentions",
            )

    for witness in _as_list(pass1.get("witnesses")):
        if not isinstance(witness, str):
            continue
        witness_node = builder.ensure_actor(
            name=witness, node_type="person", metadata={"origin": "pass1.witnesses"}
        )
        if witness_node:
            builder.add_edge(
                source=document_node_id,
                target=witness_node,
                edge_type="witness",
                label="witness",
            )

    proponent = pass1.get("proponent")
    if isinstance(proponent, str) and proponent.strip():
        proponent_node = builder.ensure_actor(
            name=proponent, node_type="person", metadata={"origin": "pass1.proponent"}
        )
        if proponent_node:
            builder.add_edge(
                source=document_node_id,
                target=proponent_node,
                edge_type="proponent",
                label="proponent",
            )

    for entity in _as_list(pass2.get("entities_enriched")):
        entity_map = _as_dict(entity)
        name = entity_map.get("name")
        if not isinstance(name, str):
            continue
        entity_node = builder.ensure_actor(
            name=name,
            node_type=_entity_kind_from_text(entity_map.get("entity_type")),
            metadata={
                "origin": "pass2.entities_enriched",
                "confidence": entity_map.get("confidence"),
            },
        )
        if entity_node:
            relation = (
                str(entity_map.get("role_hypothesis")).strip().lower().replace(" ", "_")
            )
            edge_type = relation if relation else "enriched_mention"
            builder.add_edge(
                source=document_node_id,
                target=entity_node,
                edge_type=edge_type,
                label=edge_type.replace("_", " "),
                metadata={"confidence": entity_map.get("confidence")},
            )


def _add_pass_events(
    *,
    builder: _GraphBuilder,
    document_node_id: str,
    document_uuid: str,
    pass2: dict[str, Any],
    include_statement_nodes: bool,
    include_evidence_nodes: bool,
    pass4: dict[str, Any],
) -> None:
    for idx, event in enumerate(_as_list(pass2.get("events"))):
        event_map = _as_dict(event)
        event_type = _shorten(str(event_map.get("event_type") or "Event"), max_len=52)
        event_node_id = f"event:{document_uuid}:{idx + 1}"
        event_summary = _shorten(str(event_map.get("summary") or ""), max_len=220)
        builder.ensure_node(
            node_id=event_node_id,
            label=event_type,
            node_type="event",
            metadata={
                "event_type": event_map.get("event_type"),
                "date": event_map.get("date"),
                "summary": event_summary,
                "confidence": event_map.get("confidence"),
            },
        )
        builder.add_edge(
            source=document_node_id,
            target=event_node_id,
            edge_type="has_event",
            label="has event",
            metadata={"confidence": event_map.get("confidence")},
        )
        for participant in _as_list(event_map.get("participants")):
            if not isinstance(participant, str):
                continue
            participant_node = builder.ensure_actor(
                name=participant,
                node_type="person",
                metadata={"origin": "pass2.events.participants"},
            )
            if participant_node:
                builder.add_edge(
                    source=event_node_id,
                    target=participant_node,
                    edge_type="participant",
                    label="participant",
                )

    for idx, signal in enumerate(_as_list(pass2.get("knowledge_signals"))):
        signal_map = _as_dict(signal)
        signal_type = _shorten(str(signal_map.get("type") or "Knowledge"), max_len=48)
        about = _shorten(str(signal_map.get("about") or ""), max_len=88)
        label = signal_type if not about else f"{signal_type}: {about}"
        knowledge_node_id = f"knowledge:{document_uuid}:{idx + 1}"
        builder.ensure_node(
            node_id=knowledge_node_id,
            label=label,
            node_type="knowledge",
            metadata={
                "type": signal_map.get("type"),
                "about": signal_map.get("about"),
                "time_ref": signal_map.get("time_ref"),
                "confidence": signal_map.get("confidence"),
            },
        )
        builder.add_edge(
            source=document_node_id,
            target=knowledge_node_id,
            edge_type="knowledge_signal",
            label="knowledge",
            metadata={"confidence": signal_map.get("confidence")},
        )

    if include_statement_nodes:
        for idx, statement in enumerate(_as_list(pass2.get("statements"))):
            statement_map = _as_dict(statement)
            statement_type = _shorten(
                str(statement_map.get("statement_type") or "Statement"), max_len=52
            )
            statement_node_id = f"statement:{document_uuid}:{idx + 1}"
            builder.ensure_node(
                node_id=statement_node_id,
                label=statement_type,
                node_type="statement",
                metadata={
                    "statement_type": statement_map.get("statement_type"),
                    "speaker": statement_map.get("speaker"),
                    "certainty": statement_map.get("certainty"),
                    "first_hand_likelihood": statement_map.get("first_hand_likelihood"),
                    "text_span_ref": statement_map.get("text_span_ref"),
                    "summary": _shorten(str(statement_map.get("text_span_ref") or "")),
                },
            )
            builder.add_edge(
                source=document_node_id,
                target=statement_node_id,
                edge_type="has_statement",
                label="has statement",
            )
            speaker = statement_map.get("speaker")
            if isinstance(speaker, str) and speaker.strip():
                speaker_node = builder.ensure_actor(
                    name=speaker,
                    node_type="person",
                    metadata={"origin": "pass2.statements.speaker"},
                )
                if speaker_node:
                    builder.add_edge(
                        source=statement_node_id,
                        target=speaker_node,
                        edge_type="speaker",
                        label="speaker",
                    )

    if include_evidence_nodes:
        for idx, evidence in enumerate(_as_list(pass4.get("evidence"))):
            evidence_map = _as_dict(evidence)
            quote = _shorten(str(evidence_map.get("quote") or ""), max_len=132)
            chunk_id = _shorten(str(evidence_map.get("chunk_id") or ""), max_len=64)
            label = quote or chunk_id or f"Evidence {idx + 1}"
            evidence_node_id = f"evidence:{document_uuid}:{idx + 1}"
            builder.ensure_node(
                node_id=evidence_node_id,
                label=label,
                node_type="evidence",
                metadata={
                    "quote": evidence_map.get("quote"),
                    "chunk_id": evidence_map.get("chunk_id"),
                    "page_num": evidence_map.get("page_num"),
                    "summary": quote or chunk_id,
                },
            )
            builder.add_edge(
                source=document_node_id,
                target=evidence_node_id,
                edge_type="supports",
                label="supports",
            )


def _add_fallback_document_links(
    *, builder: _GraphBuilder, document_profiles: list[_DocumentGraphProfile]
) -> int:
    if len(builder.edges) > 0 or len(document_profiles) < 2:
        return 0

    def _sort_key(profile: _DocumentGraphProfile) -> tuple[datetime, str, str]:
        raw_ingested = profile.row.get("ingested_at")
        ingested_at = raw_ingested if isinstance(raw_ingested, datetime) else datetime.min
        return (ingested_at, profile.node_display_name, profile.document_uuid)

    ordered_profiles = sorted(document_profiles, key=_sort_key)
    links_added = 0
    for left, right in zip(ordered_profiles, ordered_profiles[1:]):
        builder.add_edge(
            source=f"document:{left.document_uuid}",
            target=f"document:{right.document_uuid}",
            edge_type="related_document",
            label="related document",
            metadata={"fallback": "chronology"},
            weight=0.55,
        )
        links_added += 1
    return links_added


def build_caselaw_ontology_graph(
    *,
    session: Session,
    matter_id: str,
    max_cases: int = 2500,
) -> dict[str, Any]:
    limit = max(1, min(max_cases, 10000))
    builder = _GraphBuilder()
    pipeline_mode = "canonical"

    table_status = session.execute(
        text(
            """
            SELECT
                to_regclass('derived.caselaw_nightly_case') IS NOT NULL AS has_case_table,
                to_regclass('derived.taxonomy_node') IS NOT NULL AS has_taxonomy_table
            """
        )
    ).mappings().one()
    has_case_table = bool(table_status.get("has_case_table"))
    has_taxonomy_table = bool(table_status.get("has_taxonomy_table"))
    if not has_case_table:
        graph = builder.finalize()
        graph["meta"].update(
            {
                "matter_id": matter_id,
                "source": "postgres_caselaw",
                "documents_loaded": 0,
                "truncated_documents": False,
                "max_documents": limit,
                "reason": "missing_table:derived.caselaw_nightly_case",
                "caselaw_pipeline_mode": pipeline_mode,
                "caselaw_bootstrap_enabled": False,
                "caselaw_bootstrap_attempted": False,
            }
        )
        return graph

    taxonomy_rows: list[dict[str, Any]] = []
    latest_taxonomy_version: str | None = None
    if has_taxonomy_table:
        latest_taxonomy_version = session.execute(
            text("SELECT MAX(version) FROM derived.taxonomy_node")
        ).scalar_one_or_none()
        if latest_taxonomy_version:
            taxonomy_rows = (
                session.execute(
                    text(
                        """
                        SELECT code, label, parent_code, status
                        FROM derived.taxonomy_node
                        WHERE version = :version
                        """
                    ),
                    {"version": latest_taxonomy_version},
                )
                .mappings()
                .all()
            )

    taxonomy_labels: dict[str, str] = {}
    taxonomy_parent: dict[str, str] = {}
    taxonomy_status: dict[str, str] = {}
    for row in taxonomy_rows:
        code = str(row.get("code") or "").strip()
        if not code:
            continue
        taxonomy_labels[code] = str(row.get("label") or "").strip() or code
        parent = str(row.get("parent_code") or "").strip()
        if parent:
            taxonomy_parent[code] = parent
        status = str(row.get("status") or "").strip()
        if status:
            taxonomy_status[code] = status

    total_cases_all = session.execute(text("SELECT COUNT(*) FROM derived.caselaw_nightly_case")).scalar_one()
    total_criminal_cases = session.execute(
        text(
            """
            SELECT COUNT(*) FROM derived.caselaw_nightly_case
            WHERE lower(case_type) LIKE '%criminal%'
               OR lower(case_type) LIKE '%quasi%'
            """
        )
    ).scalar_one()
    use_criminal_filter = int(total_criminal_cases or 0) > 0

    if use_criminal_filter:
        cases = (
            session.execute(
                text(
                    """
                    SELECT
                        case_id,
                        courtlistener_cluster_id,
                        courtlistener_opinion_id,
                        court_id,
                        court_name,
                        date_filed,
                        docket_number,
                        case_name,
                        case_type,
                        taxonomy_codes,
                        taxonomy_version,
                        frontmatter_json,
                        first_ingested_at,
                        last_ingested_at
                    FROM derived.caselaw_nightly_case
                    WHERE lower(case_type) LIKE '%criminal%'
                       OR lower(case_type) LIKE '%quasi%'
                    ORDER BY date_filed DESC NULLS LAST, last_ingested_at DESC, id DESC
                    LIMIT :limit
                    """
                ),
                {"limit": limit},
            )
            .mappings()
            .all()
        )
    else:
        cases = (
            session.execute(
                text(
                    """
                    SELECT
                        case_id,
                        courtlistener_cluster_id,
                        courtlistener_opinion_id,
                        court_id,
                        court_name,
                        date_filed,
                        docket_number,
                        case_name,
                        case_type,
                        taxonomy_codes,
                        taxonomy_version,
                        frontmatter_json,
                        first_ingested_at,
                        last_ingested_at
                    FROM derived.caselaw_nightly_case
                    ORDER BY date_filed DESC NULLS LAST, last_ingested_at DESC, id DESC
                    LIMIT :limit
                    """
                ),
                {"limit": limit},
            )
            .mappings()
            .all()
        )

    court_node_ids: dict[str, str] = {}
    taxonomy_node_ids: dict[str, str] = {}

    for row in cases:
        case_id = str(row.get("case_id") or "").strip()
        if not case_id:
            continue
        case_name = str(row.get("case_name") or "").strip() or case_id
        case_node_id = f"case:{case_id}"
        frontmatter = _as_dict(row.get("frontmatter_json"))
        case_type = str(row.get("case_type") or "").strip()
        case_domain = _case_domain_from_type(case_type)
        court_id = str(row.get("court_id") or "").strip().lower()
        court_name = str(row.get("court_name") or "").strip() or court_id or "Unknown court"
        date_filed = row.get("date_filed")
        date_text = date_filed.isoformat() if hasattr(date_filed, "isoformat") else ""
        citation = _extract_primary_citation(frontmatter)
        case_summary = str(frontmatter.get("case_summary") or "").strip()
        holding = str(frontmatter.get("essential_holding") or "").strip()
        taxonomy_codes = row.get("taxonomy_codes") or []
        taxonomy_list = [str(code).strip() for code in taxonomy_codes if str(code).strip()]

        label = case_name
        if date_text:
            label = f"{label} ({date_text[:4]})"
        if citation:
            label = f"{label}, {citation}"

        builder.ensure_node(
            node_id=case_node_id,
            label=label,
            node_type="case",
            metadata={
                "case_id": case_id,
                "case_name": case_name,
                "courtlistener_cluster_id": row.get("courtlistener_cluster_id"),
                "courtlistener_opinion_id": row.get("courtlistener_opinion_id"),
                "court_id": court_id,
                "court_name": court_name,
                "date_filed": date_text,
                "docket_number": row.get("docket_number"),
                "case_type": case_type,
                "case_domain": case_domain,
                "citation": citation,
                "case_summary": case_summary,
                "essential_holding": holding,
                "taxonomy_codes": taxonomy_list,
                "taxonomy_version": row.get("taxonomy_version"),
                "summary": case_summary or holding or label,
                "first_ingested_at": (
                    row.get("first_ingested_at").isoformat()
                    if row.get("first_ingested_at") is not None
                    else None
                ),
                "last_ingested_at": (
                    row.get("last_ingested_at").isoformat()
                    if row.get("last_ingested_at") is not None
                    else None
                ),
            },
        )

        if court_id:
            court_node_id = court_node_ids.get(court_id)
            if not court_node_id:
                court_node_id = f"court:{_safe_slug(court_id)}"
                builder.ensure_node(
                    node_id=court_node_id,
                    label=court_name,
                    node_type="court",
                    metadata={
                        "court_id": court_id,
                        "court_name": court_name,
                        "summary": court_name,
                    },
                )
                court_node_ids[court_id] = court_node_id
            builder.add_edge(
                source=case_node_id,
                target=court_node_id,
                edge_type="decided_by",
                label="decided by",
                weight=1.1,
            )

        for code in taxonomy_list:
            taxonomy_node_id = taxonomy_node_ids.get(code)
            if not taxonomy_node_id:
                taxonomy_node_id = f"taxonomy:{code}"
                builder.ensure_node(
                    node_id=taxonomy_node_id,
                    label=taxonomy_labels.get(code, code),
                    node_type="taxonomy",
                    metadata={
                        "taxonomy_code": code,
                        "taxonomy_label": taxonomy_labels.get(code, code),
                        "taxonomy_parent_code": taxonomy_parent.get(code),
                        "taxonomy_status": taxonomy_status.get(code),
                        "taxonomy_version": latest_taxonomy_version or row.get("taxonomy_version"),
                        "summary": taxonomy_labels.get(code, code),
                    },
                )
                taxonomy_node_ids[code] = taxonomy_node_id
            builder.add_edge(
                source=case_node_id,
                target=taxonomy_node_id,
                edge_type="taxonomy_edge",
                label="taxonomy",
                metadata={"taxonomy_code": code},
                weight=1.3,
            )

    for code, parent_code in taxonomy_parent.items():
        parent_node_id = taxonomy_node_ids.get(parent_code)
        child_node_id = taxonomy_node_ids.get(code)
        if not parent_node_id or not child_node_id:
            continue
        builder.add_edge(
            source=child_node_id,
            target=parent_node_id,
            edge_type="taxonomy_parent",
            label="parent",
            weight=0.7,
        )

    graph = builder.finalize()
    graph["meta"].update(
        {
            "matter_id": matter_id,
            "documents_loaded": len(cases),
            "truncated_documents": len(cases) >= limit
            and int((total_criminal_cases if use_criminal_filter else total_cases_all) or 0)
            > len(cases),
            "max_documents": limit,
            "source": "postgres_caselaw",
            "total_cases": int((total_criminal_cases if use_criminal_filter else total_cases_all) or 0),
            "total_cases_all": int(total_cases_all or 0),
            "total_criminal_cases": int(total_criminal_cases or 0),
            "criminal_filter_applied": use_criminal_filter,
            "taxonomy_version": latest_taxonomy_version,
            "courts_loaded": len(court_node_ids),
            "taxonomy_nodes_loaded": len(taxonomy_node_ids),
            "casefile_mode": False,
            "caselaw_pipeline_mode": pipeline_mode,
            "caselaw_bootstrap_enabled": False,
            "caselaw_bootstrap_attempted": False,
        }
    )
    return graph


def build_matter_ontology_graph(
    *,
    session: Session,
    matter_id: str,
    max_documents: int = 2500,
    include_statement_nodes: bool = True,
    include_evidence_nodes: bool = True,
) -> dict[str, Any]:
    limit = max(1, min(max_documents, 10000))
    builder = _GraphBuilder()

    documents = session.execute(
        text(
            """
            SELECT
                dim.document_id,
                dim.original_filename,
                dim.mime_type,
                dim.file_size,
                dim.page_count,
                dim.ingested_at,
                dim.status,
                dim.pass1_metadata,
                dim.pass2_metadata,
                dim.pass4_metadata,
                d.source_path
            FROM derived.document_ingestion_metadata dim
            JOIN documents d ON d.id = dim.document_id
            WHERE dim.matter_id = :matter_id
            ORDER BY dim.ingested_at DESC NULLS LAST, dim.document_id
            LIMIT :limit
            """
        ),
        {"matter_id": matter_id, "limit": limit},
    ).mappings().all()

    token_to_documents: defaultdict[str, set[str]] = defaultdict(set)
    document_profiles: list[_DocumentGraphProfile] = []
    for raw_row in documents:
        row = dict(raw_row)
        document_uuid = str(row["document_id"])
        pass1 = _as_dict(row.get("pass1_metadata"))
        pass2 = _as_dict(row.get("pass2_metadata"))
        pass4 = _as_dict(row.get("pass4_metadata"))
        doc_type = _extract_doc_type(pass1, pass2)
        node_display_name, node_name_standard = _build_document_node_names(
            document_uuid=document_uuid,
            original_filename=_as_str(row.get("original_filename")),
            pass1=pass1,
            pass2=pass2,
            ingested_at=row.get("ingested_at"),
        )
        summary = _build_document_summary(
            original_filename=_as_str(row.get("original_filename")),
            pass1=pass1,
            pass2=pass2,
            pass4=pass4,
        )
        token_weights = _collect_relation_token_weights(
            pass1=pass1,
            pass2=pass2,
            doc_type=doc_type,
        )
        for token in token_weights:
            token_to_documents[token].add(document_uuid)

        document_profiles.append(
            _DocumentGraphProfile(
                row=row,
                document_uuid=document_uuid,
                pass1=pass1,
                pass2=pass2,
                pass4=pass4,
                doc_type=doc_type,
                node_display_name=node_display_name,
                node_name_standard=node_name_standard,
                summary=summary,
                token_weights=token_weights,
            )
        )

    profile_by_document = {profile.document_uuid: profile for profile in document_profiles}
    loaded_document_ids = set(profile_by_document.keys())

    for profile in document_profiles:
        related_scores: defaultdict[str, int] = defaultdict(int)
        for token, weight in profile.token_weights.items():
            for related_doc_id in token_to_documents.get(token, set()):
                if related_doc_id == profile.document_uuid:
                    continue
                related_scores[related_doc_id] += weight

        ranked_related = sorted(
            related_scores.items(),
            key=lambda item: (
                -item[1],
                profile_by_document[item[0]].node_display_name,
            ),
        )
        profile.related_document_ids = [doc_id for doc_id, _ in ranked_related[:6]]
        profile.related_document_names = [
            profile_by_document[doc_id].node_display_name
            for doc_id in profile.related_document_ids
        ]
        profile.frontmatter_distilled = _build_document_frontmatter_distilled(
            row=profile.row,
            pass1=profile.pass1,
            pass2=profile.pass2,
            pass4=profile.pass4,
            doc_type=profile.doc_type,
            node_display_name=profile.node_display_name,
            node_name_standard=profile.node_name_standard,
            summary=profile.summary,
            related_document_names=profile.related_document_names,
            related_document_ids=profile.related_document_ids,
        )

    entities = session.execute(
        select(
            Entity.id,
            Entity.canonical_name,
            Entity.entity_type,
            Entity.aliases_json,
        )
        .join(DocumentEntity, DocumentEntity.entity_id == Entity.id)
        .join(Document, Document.id == DocumentEntity.document_id)
        .where(
            Entity.matter_id == matter_id,
            Document.matter_id == matter_id,
        )
        .group_by(Entity.id)
    ).all()
    entity_lookup: dict[str, str] = {}
    for entity in entities:
        entity_id = f"entity:{entity.id}"
        entity_kind = _entity_kind_from_text(getattr(entity.entity_type, "value", ""))
        builder.ensure_node(
            node_id=entity_id,
            label=entity.canonical_name,
            node_type=entity_kind,
            metadata={
                "entity_id": str(entity.id),
                "entity_type": getattr(entity.entity_type, "value", entity.entity_type),
                "aliases": entity.aliases_json,
            },
        )
        builder.register_entity_name(name=entity.canonical_name, node_id=entity_id)
        entity_lookup[str(entity.id)] = entity_id

    for profile in document_profiles:
        row = profile.row
        document_uuid = profile.document_uuid
        document_node_id = f"document:{document_uuid}"
        pass1 = profile.pass1
        pass2 = profile.pass2
        pass4 = profile.pass4

        builder.ensure_node(
            node_id=document_node_id,
            label=profile.node_display_name,
            node_type="document",
            metadata={
                "document_id": document_uuid,
                "original_filename": row["original_filename"],
                "source_path": row["source_path"],
                "mime_type": row["mime_type"],
                "status": getattr(row["status"], "value", row["status"]),
                "file_size": row["file_size"],
                "page_count": row["page_count"],
                "ingested_at": (
                    row["ingested_at"].isoformat() if row["ingested_at"] is not None else None
                ),
                "node_name_standard": profile.node_name_standard,
                "summary": profile.summary,
                "frontmatter_distilled": profile.frontmatter_distilled,
            },
        )

        _add_document_metadata_topics(
            builder=builder,
            document_node_id=document_node_id,
            pass1=pass1,
            pass2=pass2,
            pass4=pass4,
        )
        _add_authorship_links(
            builder=builder,
            document_node_id=document_node_id,
            pass1=pass1,
        )
        _add_pass_entities(
            builder=builder,
            document_node_id=document_node_id,
            pass1=pass1,
            pass2=pass2,
        )
        _add_pass_events(
            builder=builder,
            document_node_id=document_node_id,
            document_uuid=document_uuid,
            pass2=pass2,
            include_statement_nodes=include_statement_nodes,
            include_evidence_nodes=include_evidence_nodes,
            pass4=pass4,
        )

    relations = session.execute(
        select(
            DocumentEntity.document_id,
            DocumentEntity.entity_id,
            DocumentEntity.role,
            DocumentEntity.confidence,
        )
        .join(Document, Document.id == DocumentEntity.document_id)
        .join(Entity, Entity.id == DocumentEntity.entity_id)
        .where(
            Entity.matter_id == matter_id,
            Document.matter_id == matter_id,
        )
    ).all()
    for relation in relations:
        document_id = str(relation.document_id)
        if loaded_document_ids and document_id not in loaded_document_ids:
            continue
        document_node_id = f"document:{document_id}"
        entity_node_id = entity_lookup.get(str(relation.entity_id))
        if not entity_node_id:
            continue
        edge_type = (
            str(getattr(relation.role, "value", relation.role)).strip().lower() or "linked_entity"
        )
        builder.add_edge(
            source=document_node_id,
            target=entity_node_id,
            edge_type=edge_type,
            label=edge_type.replace("_", " "),
            metadata={"confidence": relation.confidence},
            weight=1.2,
        )

    exhibits = session.execute(
        select(
            Exhibit.id,
            Exhibit.document_id,
            Exhibit.purpose,
            Exhibit.notes,
        )
        .join(Document, Document.id == Exhibit.document_id)
        .where(
            Exhibit.matter_id == matter_id,
            Document.matter_id == matter_id,
        )
    ).all()
    for exhibit in exhibits:
        document_id = str(exhibit.document_id)
        if loaded_document_ids and document_id not in loaded_document_ids:
            continue
        exhibit_node_id = f"exhibit:{exhibit.id}"
        purpose = getattr(exhibit.purpose, "value", exhibit.purpose)
        builder.ensure_node(
            node_id=exhibit_node_id,
            label=f"Exhibit {str(exhibit.id)[:8]}",
            node_type="exhibit",
            metadata={
                "exhibit_id": str(exhibit.id),
                "purpose": purpose,
                "notes": exhibit.notes,
                "summary": _shorten(f"{purpose or 'EXHIBIT'} • {exhibit.notes or ''}", max_len=180),
            },
        )
        document_node_id = f"document:{document_id}"
        builder.add_edge(
            source=exhibit_node_id,
            target=document_node_id,
            edge_type="exhibit_of",
            label="exhibit of",
        )
        if isinstance(purpose, str) and purpose.strip():
            purpose_node = _add_topic(builder, label=purpose.strip(), topic_kind="topic")
            builder.add_edge(
                source=exhibit_node_id,
                target=purpose_node,
                edge_type="purpose",
                label="purpose",
            )

    fallback_document_links_added = _add_fallback_document_links(
        builder=builder,
        document_profiles=document_profiles,
    )

    graph = builder.finalize()
    graph["meta"].update(
        {
            "matter_id": matter_id,
            "documents_loaded": len(documents),
            "truncated_documents": len(documents) >= limit,
            "max_documents": limit,
            "source": "casefile_schema",
            "casefile_mode": True,
            "include_statement_nodes": include_statement_nodes,
            "include_evidence_nodes": include_evidence_nodes,
            "fallback_document_links_added": fallback_document_links_added,
            "document_node_naming_standard": (
                "DOC::{YYYY_MM_DD|UNDATED}::{DOCUMENT_TYPE}::{TITLE}"
            ),
        }
    )
    return graph
