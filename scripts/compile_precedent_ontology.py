#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from acquittify.metadata_extract import normalize_citation
from acquittify.ontology.authority_extract import extract_authority_mentions
from acquittify.ontology.anchor_scope import (
    SyllabusSpan,
    extract_authority_mentions_syllabus_first,
    extract_citation_mentions_syllabus_first,
)
from acquittify.ontology.canonicalize import canonicalize_issues
from acquittify.ontology.circuit_origin import extract_originating_circuit
from acquittify.ontology.config import OntologyConfig
from acquittify.ontology.citation_extract import extract_citation_mentions
from acquittify.ontology.citation_roles import classify_citation_roles
from acquittify.ontology.citation_resolver import CitationResolver
from acquittify.ontology.extractor import extract_structures, parse_extraction_json
from acquittify.ontology.ids import build_case_id, build_holding_id, stable_hash
from acquittify.ontology.metrics import apply_metrics, load_params
from acquittify.ontology.relations import build_relation_nodes
from acquittify.ontology.schemas import (
    AuthorityAnchor,
    CaseNode,
    CitationAnchor,
    HoldingNode,
    SecondaryNode,
    SourceNode,
    SourceType,
)
from acquittify.ontology.taxonomy_case_map import map_case_taxonomies
from acquittify.ontology.vault_writer import VaultWriter


def _ensure_vault_structure(vault_root: Path) -> None:
    required_dirs = [
        "cases/scotus",
        "cases/circuits",
        "cases/districts",
        "holdings",
        "issues/taxonomy",
        "issues/instances",
        "sources/constitution",
        "sources/statutes",
        "sources/regs",
        "sources/secondary",
        "relations",
        "events/interpretations",
        "indices",
    ]
    for relative in required_dirs:
        (vault_root / relative).mkdir(parents=True, exist_ok=True)


def _read_input_text(path: Path | None) -> str:
    if not path:
        return ""
    return path.read_text(encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compile citation-anchored precedent ontology artifacts.")
    parser.add_argument("--text-file", type=Path, help="Opinion text input file", default=None)
    parser.add_argument("--citation", action="append", default=[], help="Manual citation input")
    parser.add_argument("--vault-root", type=Path, default=None, help="Override ontology vault root")
    parser.add_argument("--output", type=Path, default=None, help="Write run output JSON to file")
    parser.add_argument("--skip-resolver", action="store_true", help="Skip citation resolution API calls")
    parser.add_argument("--run-extractor", action="store_true", help="Run LLM structured extraction")
    parser.add_argument("--extraction-json", type=Path, default=None, help="Use pre-generated extraction JSON")
    parser.add_argument("--title", default=None, help="Case title")
    parser.add_argument("--court", default="SCOTUS", help="Court label")
    parser.add_argument("--court-level", default="supreme", help="Court level (supreme|circuit|district)")
    parser.add_argument("--jurisdiction", default="US", help="Jurisdiction label")
    parser.add_argument("--date-decided", default="0000-01-01", help="Decision date (YYYY-MM-DD)")
    parser.add_argument("--publication-status", default="published", help="Publication status")
    parser.add_argument("--opinion-type", default="majority", help="Opinion type")
    parser.add_argument("--primary-citation", default=None, help="Primary citation for case ID construction")
    parser.add_argument("--case-id", default=None, help="Optional explicit case_id override for idempotent recompiles")
    parser.add_argument("--opinion-pdf-path", default=None, help="Absolute or vault-relative path to the source opinion PDF")
    parser.add_argument("--params-file", type=Path, default=None, help="Optional params YAML/JSON path for metrics")
    parser.add_argument("--dry-run", action="store_true", help="Skip writing vault files")
    return parser


def _default_title(args, text_file: Path | None) -> str:
    if args.title and args.title.strip():
        return args.title.strip()
    if text_file:
        return text_file.stem.replace("_", " ")
    return "Untitled Case"


_WHITESPACE_RE = re.compile(r"\s+")
_US_CITATION_RE = re.compile(r"\b\d{1,4}\s+U\.?\s*S\.?\s+\d+\b", re.IGNORECASE)
_HELD_LINE_RE = re.compile(r"\bHeld:\s*(.+)$", re.IGNORECASE)
SYLLABUS_CITATION_MIN_MENTIONS = 4
SYLLABUS_AUTHORITY_MIN_MENTIONS = 3


def _compact_text(value: str, max_len: int) -> str:
    text = _WHITESPACE_RE.sub(" ", str(value or "")).strip()
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return f"{text[: max(0, max_len - 1)].rstrip()}…"


def _first_sentence(value: str, max_len: int = 420) -> str:
    text = _compact_text(value, max_len=max_len * 2)
    if not text:
        return ""
    sentences = re.findall(r"[^.!?]+[.!?]", text)
    candidate = ""
    for sentence in sentences:
        cleaned = _compact_text(sentence, max_len)
        if len(cleaned) >= 24:
            candidate = cleaned
            break
    if not candidate:
        match = re.search(r"^(.+?[.!?])(?:\s+|$)", text)
        candidate = match.group(1) if match else text
    return _compact_text(candidate, max_len)


def _extract_held_text(opinion_text: str) -> str:
    lines = (opinion_text or "").splitlines()
    if not lines:
        return ""

    scan_limit = min(len(lines), 900)
    for idx in range(scan_limit):
        line = lines[idx]
        match = _HELD_LINE_RE.search(line)
        if not match:
            continue

        collected = [_compact_text(match.group(1), 800)]
        for follow in lines[idx + 1 : min(idx + 9, len(lines))]:
            item = _compact_text(follow, 240)
            if not item:
                break
            lower = item.lower()
            if lower.startswith(("pp.", "judgment", "certiorari", "argued", "decided", "on writ")):
                break
            if re.fullmatch(r"[A-Z][A-Z\s.]{8,}", item):
                break
            collected.append(item)
            if len(" ".join(collected)) >= 820:
                break

        text = _compact_text(" ".join(collected), 820)
        text = re.sub(r"\s+Pp\.\s*\d+[\-–]\d+\.?\s*", " ", text)
        return _compact_text(text, 820)
    return ""


def _fallback_summary_from_text(opinion_text: str, case_title: str, case_citation: str) -> str:
    held_text = _extract_held_text(opinion_text)
    if held_text:
        return _compact_text(held_text, 680)

    compact = _compact_text(opinion_text, 12000)
    if compact:
        for pattern in (
            r"\bwe hold that\b(.+?[.!?])",
            r"\bthe Court holds that\b(.+?[.!?])",
            r"\bthe Court concludes that\b(.+?[.!?])",
        ):
            match = re.search(pattern, compact, flags=re.IGNORECASE)
            if match:
                return _compact_text(match.group(0), 680)

        paragraphs = [item.strip() for item in re.split(r"\n\s*\n", opinion_text or "") if item.strip()]
        skip_markers = (
            "SUPREME COURT OF THE UNITED STATES",
            "Syllabus",
            "NOTICE:",
            "OCTOBER TERM",
            "Cite as:",
        )
        for paragraph in paragraphs[:80]:
            candidate = _compact_text(paragraph, 800)
            if len(candidate) < 70:
                continue
            if any(marker.lower() in candidate.lower() for marker in skip_markers):
                continue
            if "." not in candidate:
                continue
            return _compact_text(candidate, 680)

    title = _compact_text(case_title, 140) or "This case"
    citation = _compact_text(case_citation, 80)
    if citation:
        return f"{title} ({citation}). Structured holdings are not yet extracted for this case."
    return f"{title}. Structured holdings are not yet extracted for this case."


def _is_scotus_reporter_citation(normalized_citation: str) -> bool:
    return bool(_US_CITATION_RE.search(normalized_citation or ""))


def _build_case_citation_anchors(
    mentions: list,
    resolved_case_map: dict[str, str | None],
    citation_role_map: dict[str, str],
    case_id: str,
    resolver_confidence_map: dict[str, float],
) -> list[CitationAnchor]:
    anchors: list[CitationAnchor] = []
    seen: set[tuple[int | None, int | None, str, str | None]] = set()

    for mention in mentions:
        normalized = normalize_citation(getattr(mention, "normalized_text", "") or getattr(mention, "raw_text", ""))
        if not normalized or not _is_scotus_reporter_citation(normalized):
            continue
        resolved_case_id = resolved_case_map.get(normalized)
        if resolved_case_id == case_id:
            continue

        start_char = getattr(mention, "start_char", None)
        end_char = getattr(mention, "end_char", None)
        dedup_key = (start_char, end_char, normalized, resolved_case_id)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        role = citation_role_map.get(normalized)
        confidence = resolver_confidence_map.get(normalized)
        if confidence is None:
            confidence = 0.95 if resolved_case_id else 0.0

        anchors.append(
            CitationAnchor(
                raw_text=str(getattr(mention, "raw_text", "") or normalized),
                normalized_text=normalized,
                resolved_case_id=resolved_case_id,
                confidence=max(0.0, min(1.0, float(confidence))),
                start_char=int(start_char) if isinstance(start_char, int) else None,
                end_char=int(end_char) if isinstance(end_char, int) else None,
                role=role,
            )
        )

    anchors.sort(key=lambda item: (item.start_char or -1, item.end_char or -1, item.normalized_text))
    return anchors


def _build_case_authority_anchors(authority_mentions: list) -> list[AuthorityAnchor]:
    anchors: list[AuthorityAnchor] = []
    seen: set[tuple[int | None, int | None, str]] = set()
    for mention in authority_mentions:
        source_id = str(getattr(mention, "source_id", "") or "").strip()
        normalized = str(getattr(mention, "normalized_text", "") or "").strip()
        if not source_id or not normalized:
            continue
        start_char = getattr(mention, "start_char", None)
        end_char = getattr(mention, "end_char", None)
        dedup_key = (
            int(start_char) if isinstance(start_char, int) else None,
            int(end_char) if isinstance(end_char, int) else None,
            source_id,
        )
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        anchors.append(
            AuthorityAnchor(
                raw_text=str(getattr(mention, "raw_text", "") or normalized),
                normalized_text=normalized,
                source_id=source_id,
                source_type=str(getattr(mention, "source_type", "") or "other"),
                confidence=max(0.0, min(1.0, float(getattr(mention, "confidence", 0.0) or 0.0))),
                start_char=int(start_char) if isinstance(start_char, int) else None,
                end_char=int(end_char) if isinstance(end_char, int) else None,
                extractor=str(getattr(mention, "extractor", "") or "regex"),
            )
        )
    anchors.sort(key=lambda item: (item.start_char or -1, item.end_char or -1, item.source_id))
    return anchors


def _build_case_node(
    args,
    all_citations: list[str],
    text_file: Path | None,
    opinion_text: str,
    extraction,
    citation_anchors: list[CitationAnchor],
    authority_anchors: list[AuthorityAnchor],
    interpretive_edges: list[dict],
) -> CaseNode:
    title = _default_title(args, text_file)
    primary_citation = args.primary_citation or (all_citations[0] if all_citations else "unknown")
    originating_circuit, originating_circuit_label = extract_originating_circuit(opinion_text)
    case_id = str(args.case_id or "").strip()
    if not case_id:
        case_id = build_case_id(
            jurisdiction=args.jurisdiction,
            court=args.court,
            date_decided=args.date_decided,
            title=title,
            primary_citation=primary_citation,
        )
    essential_holding = ""
    if extraction and extraction.holdings:
        essential_holding = _compact_text(extraction.holdings[0].holding_text, 420)
    if not essential_holding:
        essential_holding = _first_sentence(_extract_held_text(opinion_text), 420)

    case_summary = ""
    if extraction and extraction.holdings:
        summary_seed = " ".join(
            _compact_text(item.holding_text, 380)
            for item in extraction.holdings[:2]
            if _compact_text(item.holding_text, 380)
        )
        case_summary = _compact_text(summary_seed, 680)
    if not case_summary:
        case_summary = _fallback_summary_from_text(opinion_text, title, primary_citation)
    if not essential_holding:
        essential_holding = _first_sentence(case_summary, 420)

    return CaseNode(
        case_id=case_id,
        title=title,
        court=args.court,
        court_level=args.court_level,
        jurisdiction=args.jurisdiction,
        date_decided=args.date_decided,
        publication_status=args.publication_status,
        opinion_type=args.opinion_type,
        originating_circuit=originating_circuit,
        originating_circuit_label=originating_circuit_label,
        judges={"author": "", "joining": []},
        citations_in_text=all_citations,
        case_summary=case_summary,
        essential_holding=essential_holding,
        citation_anchors=citation_anchors,
        authority_anchors=authority_anchors,
        interpretive_edges=interpretive_edges,
        sources={
            "opinion_text_source": "local_file" if text_file else "unknown",
            "opinion_url": str(text_file) if text_file else "",
            "opinion_pdf_path": str(args.opinion_pdf_path or "").strip(),
            "primary_citation": primary_citation,
        },
    )


def _build_holding_nodes(case_node: CaseNode, extraction, resolved_case_map: dict[str, str | None]) -> list[HoldingNode]:
    court_level = (case_node.court_level or "").lower()
    if "supreme" in court_level:
        base_weight = 1.0
    elif "circuit" in court_level:
        base_weight = 0.8
    elif "district" in court_level:
        base_weight = 0.5
    else:
        base_weight = 0.3

    holdings: list[HoldingNode] = []
    for idx, item in enumerate(extraction.holdings, start=1):
        holding_id = build_holding_id(case_node.case_id, idx)

        supporting_ids: list[str] = []
        for citation in item.citations_supporting:
            normalized = normalize_citation(citation)
            supporting_ids.append(resolved_case_map.get(normalized) or normalized)

        normative_source = sorted(
            {
                source_id.strip()
                for source_id in (
                    list(item.normative_source or [])
                    + [source.source_id for source in (item.secondary_sources or []) if source.source_id]
                )
                if isinstance(source_id, str) and source_id.strip()
            }
        )

        holdings.append(
            HoldingNode(
                holding_id=holding_id,
                case_id=case_node.case_id,
                normative_source=normative_source,
                holding_text=item.holding_text,
                if_condition=[{"predicate": p.predicate, "value": p.value} for p in item.if_condition],
                then_consequence=[{"predicate": p.predicate, "value": p.value} for p in item.then_consequence],
                normative_strength=item.normative_strength,
                standard_of_review=None,
                burden={"party": None, "level": None},
                fact_vector=[{"dimension": f.dimension, "value": f.value} for f in item.fact_vector],
                authority={
                    "base_weight": base_weight,
                    "modifiers": {"publication": 1.0, "majority_type": 1.0},
                    "final_weight": base_weight,
                },
                anchors={
                    "doctrinal_root": {
                        "root_case_id": case_node.case_id,
                        "root_holding_id": build_holding_id(case_node.case_id, 1),
                    }
                },
                source_links=[],
                citations_supporting=supporting_ids,
                metrics={},
            )
        )
    return holdings


def _source_type_from_id(source_id: str) -> SourceType:
    normalized = (source_id or "").strip().lower()
    if normalized.startswith("constitution."):
        return SourceType.constitution
    if normalized.startswith("statute.") or normalized.startswith("statutes."):
        return SourceType.statute
    if normalized.startswith("reg.") or normalized.startswith("regs.") or normalized.startswith("regulation."):
        return SourceType.reg
    if normalized.startswith("secondary."):
        return SourceType.secondary
    return SourceType.other


def _source_type_from_authority_kind(kind: str) -> SourceType:
    normalized = str(kind or "").strip().lower()
    if normalized == "constitution":
        return SourceType.constitution
    if normalized in {"statute", "public_law", "statutes_at_large"}:
        return SourceType.statute
    if normalized in {"reg", "rule", "guideline"}:
        return SourceType.reg
    return SourceType.other


def _source_weight(source_type: SourceType, params: dict) -> float:
    source_multipliers = params.get("source_type_multiplier", {}) or {}
    authority_weights = params.get("authority_weights", {}) or {}
    if source_type == SourceType.secondary:
        return float(authority_weights.get("secondary", source_multipliers.get("secondary", 0.3)))
    return float(source_multipliers.get(source_type.value, 1.0))


def _build_source_nodes_and_link_holdings(holdings: list[HoldingNode], extraction, params: dict) -> tuple[list[SourceNode | SecondaryNode], list[HoldingNode]]:
    secondary_meta: dict[str, dict] = {}
    if extraction:
        for extracted_holding in extraction.holdings:
            for secondary in extracted_holding.secondary_sources or []:
                sid = (secondary.source_id or "").strip()
                if not sid or sid in secondary_meta:
                    continue
                secondary_meta[sid] = {
                    "title": secondary.title,
                    "topic_tags": list(secondary.topic_tags or []),
                }

    source_nodes_by_id: dict[str, SourceNode | SecondaryNode] = {}
    updated_holdings: list[HoldingNode] = []

    for holding in holdings:
        links = []
        for source_id in sorted(set(holding.normative_source or [])):
            source_type = _source_type_from_id(source_id)
            weight = _source_weight(source_type, params)
            links.append({"source_id": source_id, "weight": weight, "role": "normative_source"})

            if source_type == SourceType.secondary:
                meta = secondary_meta.get(source_id, {})
                title = str(meta.get("title") or source_id)
                topic_tags = sorted(set(str(tag) for tag in (meta.get("topic_tags") or []) if str(tag).strip()))
                source_nodes_by_id[source_id] = SecondaryNode(
                    source_id=source_id,
                    title=title,
                    authority_weight=weight,
                    topic_tags=topic_tags,
                )
            else:
                source_nodes_by_id[source_id] = SourceNode(
                    source_id=source_id,
                    source_type=source_type,
                    title=None,
                    authority_weight=weight,
                    topic_tags=[],
                )

        payload = holding.model_dump() if hasattr(holding, "model_dump") else holding.dict()
        payload["source_links"] = links
        updated_holdings.append(HoldingNode(**payload))

    sources = sorted(source_nodes_by_id.values(), key=lambda item: item.source_id)
    return sources, updated_holdings


def _build_source_nodes_from_authority_anchors(
    authority_anchors: list[AuthorityAnchor],
    params: dict,
) -> list[SourceNode]:
    by_source_id: dict[str, SourceNode] = {}
    for anchor in authority_anchors:
        source_id = str(anchor.source_id or "").strip()
        if not source_id:
            continue
        source_type = _source_type_from_authority_kind(anchor.source_type)
        title = str(anchor.normalized_text or source_id).strip() or source_id
        by_source_id[source_id] = SourceNode(
            source_id=source_id,
            source_type=source_type,
            title=title,
            authority_weight=_source_weight(source_type, params),
            topic_tags=[],
        )
    return sorted(by_source_id.values(), key=lambda item: item.source_id)


def _merge_source_nodes(
    first: list[SourceNode | SecondaryNode],
    second: list[SourceNode | SecondaryNode],
) -> list[SourceNode | SecondaryNode]:
    merged: dict[str, SourceNode | SecondaryNode] = {}
    for item in list(first) + list(second):
        key = str(getattr(item, "source_id", "") or "").strip()
        if not key:
            continue
        merged[key] = item
    return sorted(merged.values(), key=lambda item: item.source_id)


def _normalize_text_key(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _is_compatible_source_for_authority_type(source_id: str, authority_type: str) -> bool:
    sid = str(source_id or "").strip().lower()
    atype = str(authority_type or "").strip().upper()
    if atype == "CONSTITUTION":
        return sid.startswith("constitution.")
    if atype == "STATUTE":
        return sid.startswith("statute.")
    if atype == "REGULATION":
        return sid.startswith("reg.")
    if atype == "FEDERAL_RULE":
        return sid.startswith("rule.")
    return False


def _source_type_from_interpretive_authority_type(authority_type: str) -> SourceType:
    atype = str(authority_type or "").strip().upper()
    if atype == "CONSTITUTION":
        return SourceType.constitution
    if atype == "STATUTE":
        return SourceType.statute
    if atype in {"REGULATION", "FEDERAL_RULE"}:
        return SourceType.reg
    return SourceType.other


def _resolve_target_source_id_from_interpretive_edge(
    target_authority: str,
    authority_type: str,
    authority_anchors: list[AuthorityAnchor],
) -> tuple[str, str, str]:
    target_raw = str(target_authority or "").strip()
    if not target_raw:
        return "", "", ""

    normalized_lookup: dict[str, tuple[str, str, str]] = {}
    for anchor in authority_anchors:
        key = _normalize_text_key(anchor.normalized_text)
        if key and key not in normalized_lookup:
            normalized_lookup[key] = (
                str(anchor.source_id or "").strip(),
                str(anchor.normalized_text or "").strip(),
                str(anchor.source_type or "").strip(),
            )

    exact = normalized_lookup.get(_normalize_text_key(target_raw))
    if exact and _is_compatible_source_for_authority_type(exact[0], authority_type):
        return exact

    mentions = extract_authority_mentions(target_raw)
    for mention in mentions:
        source_id = str(getattr(mention, "source_id", "") or "").strip()
        normalized_text = str(getattr(mention, "normalized_text", "") or target_raw).strip()
        source_type = str(getattr(mention, "source_type", "") or "").strip()
        if not source_id:
            continue
        if _is_compatible_source_for_authority_type(source_id, authority_type):
            return source_id, normalized_text, source_type

    return "", "", ""


def _resolve_target_case_id_from_interpretive_edge(target_authority: str, resolved_case_map: dict[str, str | None]) -> str:
    raw = str(target_authority or "").strip()
    if not raw:
        return ""
    if raw.startswith("us.") or raw.startswith("courtlistener."):
        return raw
    normalized = normalize_citation(raw)
    candidate = str(resolved_case_map.get(normalized) or "").strip() if normalized else ""
    if candidate:
        return candidate
    mentions = extract_citation_mentions(raw)
    for mention in mentions:
        value = str(resolved_case_map.get(str(mention.normalized_text or "").strip()) or "").strip()
        if value:
            return value
    return ""


def _build_interpretive_edges(
    extraction,
    case_id: str,
    authority_anchors: list[AuthorityAnchor],
    resolved_case_map: dict[str, str | None],
    params: dict,
) -> tuple[list[dict[str, Any]], list[SourceNode], list[dict[str, Any]]]:
    edges: list[dict[str, Any]] = []
    source_nodes_by_id: dict[str, SourceNode] = {}
    unresolved: list[dict[str, Any]] = []

    extracted = list(getattr(extraction, "interpretive_edges", []) or []) if extraction else []
    for index, edge in enumerate(extracted):
        source_case = str(getattr(edge, "source_case", "") or "").strip() or case_id
        if source_case != case_id:
            source_case = case_id
        authority_type = str(getattr(edge, "authority_type", "") or "").strip().upper()
        edge_type = str(getattr(edge, "edge_type", "") or "").strip().upper()
        target_authority = str(getattr(edge, "target_authority", "") or "").strip()
        text_span = _compact_text(str(getattr(edge, "text_span", "") or ""), 800)
        confidence = max(0.0, min(1.0, float(getattr(edge, "confidence", 0.65) or 0.65)))

        payload: dict[str, Any] = {
            "source_case": source_case,
            "target_authority": target_authority,
            "authority_type": authority_type,
            "edge_type": edge_type,
            "confidence": confidence,
            "text_span": text_span,
        }

        if authority_type == "PRIOR_CASE":
            target_case_id = _resolve_target_case_id_from_interpretive_edge(target_authority, resolved_case_map)
            if not target_case_id:
                unresolved.append(
                    {
                        "type": "interpretive_edge_unresolved",
                        "reason": "target_case_not_resolved",
                        "source_case": source_case,
                        "target_authority": target_authority,
                        "authority_type": authority_type,
                        "edge_type": edge_type,
                        "source_index": index,
                    }
                )
                continue
            payload["target_case_id"] = target_case_id
            edges.append(payload)
            continue

        source_id, normalized_authority, source_kind = _resolve_target_source_id_from_interpretive_edge(
            target_authority=target_authority,
            authority_type=authority_type,
            authority_anchors=authority_anchors,
        )
        if not source_id:
            unresolved.append(
                {
                    "type": "interpretive_edge_unresolved",
                    "reason": "target_authority_not_resolved",
                    "source_case": source_case,
                    "target_authority": target_authority,
                    "authority_type": authority_type,
                    "edge_type": edge_type,
                    "source_index": index,
                }
            )
            continue

        payload["target_source_id"] = source_id
        if normalized_authority:
            payload["normalized_target_authority"] = normalized_authority
        if source_kind:
            payload["target_source_type"] = source_kind
        edges.append(payload)

        source_type = _source_type_from_interpretive_authority_type(authority_type)
        title = normalized_authority or target_authority or source_id
        source_nodes_by_id[source_id] = SourceNode(
            source_id=source_id,
            source_type=source_type,
            title=title,
            authority_weight=_source_weight(source_type, params),
            topic_tags=[],
        )

    source_nodes = sorted(source_nodes_by_id.values(), key=lambda item: item.source_id)
    return edges, source_nodes, unresolved


def _interpretive_events_from_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for item in edges:
        events.append({"type": "interpretive_edge", **item})
    return events


def _build_citation_role_map(role_assignments: list) -> dict[str, str]:
    role_map: dict[str, tuple[str, float]] = {}
    for item in role_assignments:
        key = item.mention.normalized_text
        candidate = (item.role.value, float(item.confidence))
        existing = role_map.get(key)
        if existing is None or candidate[1] > existing[1]:
            role_map[key] = candidate
    return {key: value[0] for key, value in role_map.items()}


def _merge_local_case_resolution(
    all_citations: list[str],
    resolved_case_map: dict[str, str | None],
    local_case_citation_map: dict[str, str],
) -> dict[str, str | None]:
    merged = dict(resolved_case_map)
    for citation in all_citations:
        normalized = normalize_citation(citation)
        local_case_id = local_case_citation_map.get(normalized)
        if not local_case_id:
            continue
        existing = str(merged.get(normalized) or "").strip()
        # Prefer local ontology case IDs over external resolver IDs.
        if not existing or existing.startswith("courtlistener."):
            merged[normalized] = local_case_id
    return merged


def _remap_resolver_results_to_local_case_ids(
    resolved_items: list,
    resolved_case_map: dict[str, str | None],
    local_case_citation_map: dict[str, str],
) -> dict[str, str | None]:
    remapped = dict(resolved_case_map)
    for item in resolved_items or []:
        normalized = normalize_citation(getattr(item, "normalized_citation", "") or "")
        if not normalized:
            continue

        current = str(remapped.get(normalized) or "").strip()
        if current and not current.startswith("courtlistener."):
            continue

        canonical = normalize_citation(getattr(item, "canonical_citation", "") or "")
        local_case_id = local_case_citation_map.get(canonical) if canonical else None
        if local_case_id:
            remapped[normalized] = local_case_id
    return remapped


def _build_relation_citation_mentions(mentions: list, citation_role_map: dict[str, str], resolved_case_map: dict[str, str | None]) -> list[dict]:
    enriched: list[dict] = []
    for mention in mentions:
        resolved_case_id = resolved_case_map.get(mention.normalized_text)
        if not resolved_case_id:
            continue
        enriched.append(
            {
                "normalized_text": mention.normalized_text,
                "start_char": mention.start_char,
                "end_char": mention.end_char,
                "resolved_case_id": resolved_case_id,
                "role": citation_role_map.get(mention.normalized_text),
            }
        )
    return enriched


def _review_defaults_for_item(item: dict) -> dict[str, str]:
    item_type = str(item.get("type", "")).lower()
    reason = str(item.get("reason", "")).lower()

    if item_type == "citation_unresolved":
        if reason == "no_resolution":
            return {
                "category": "citation_resolution",
                "severity": "high",
                "review_action": "resolve_citation_anchor",
            }
        return {
            "category": "citation_resolution",
            "severity": "medium",
            "review_action": "verify_citation_confidence",
        }

    if item_type == "relation_unresolved":
        if reason in {"target_holding_inference_failed", "target_holding_id_not_found", "source_holding_id_not_found"}:
            return {
                "category": "relation_targeting",
                "severity": "high",
                "review_action": "confirm_relation_target",
            }
        return {
            "category": "relation_targeting",
            "severity": "medium",
            "review_action": "validate_relation_indices",
        }

    if item_type == "issue_unresolved":
        if reason == "minimality_reject":
            return {
                "category": "issue_minimality",
                "severity": "low",
                "review_action": "confirm_non_doctrinal_issue",
            }
        return {
            "category": "issue_mapping",
            "severity": "medium",
            "review_action": "review_issue_canonicalization",
        }

    if item_type == "extraction_unresolved":
        return {
            "category": "extraction_failure",
            "severity": "high",
            "review_action": "inspect_extractor_output",
        }

    if item_type == "interpretive_edge_unresolved":
        if reason == "target_case_not_resolved":
            return {
                "category": "interpretive_mapping",
                "severity": "high",
                "review_action": "resolve_interpretive_target_case",
            }
        return {
            "category": "interpretive_mapping",
            "severity": "medium",
            "review_action": "resolve_interpretive_target_authority",
        }

    return {
        "category": "manual_review",
        "severity": "medium",
        "review_action": "manual_review",
    }


def _review_identity_fields(item: dict) -> dict:
    keys = (
        "type",
        "reason",
        "normalized_citation",
        "normalized_form",
        "source_case",
        "target_authority",
        "authority_type",
        "edge_type",
        "source_index",
        "source_holding_index",
        "target_holding_index",
        "source_holding_id",
        "target_holding_id",
        "case_id",
    )
    return {key: item.get(key) for key in keys if key in item}


def _enrich_unresolved_items(unresolved_items: list[dict]) -> list[dict]:
    enriched: list[dict] = []
    seen_ids: set[str] = set()

    for item in unresolved_items:
        payload = dict(item)
        defaults = _review_defaults_for_item(payload)
        payload["type"] = str(payload.get("type", "unresolved")).lower()
        payload["reason"] = str(payload.get("reason", "unknown")).lower()
        payload["category"] = str(payload.get("category") or defaults["category"])
        payload["severity"] = str(payload.get("severity") or defaults["severity"]).lower()
        payload["review_action"] = str(payload.get("review_action") or defaults["review_action"])
        payload["status"] = str(payload.get("status") or "open").lower()

        if not payload.get("review_id"):
            identity_seed = json.dumps(
                _review_identity_fields(payload),
                ensure_ascii=False,
                sort_keys=True,
            )
            payload["review_id"] = f"review.{payload['type']}.{stable_hash(identity_seed, size=12)}"

        review_id = str(payload.get("review_id"))
        if review_id in seen_ids:
            continue
        seen_ids.add(review_id)
        enriched.append(payload)

    def _severity_rank(value: str) -> int:
        ranks = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        return ranks.get((value or "").lower(), 9)

    return sorted(
        enriched,
        key=lambda item: (
            _severity_rank(str(item.get("severity", ""))),
            str(item.get("category", "")),
            str(item.get("reason", "")),
            str(item.get("review_id", "")),
        ),
    )


def _count_unresolved_by_severity(unresolved_items: list[dict]) -> dict[str, int]:
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for item in unresolved_items:
        key = str(item.get("severity", "medium")).lower()
        if key not in counts:
            key = "medium"
        counts[key] += 1
    counts["total"] = len(unresolved_items)
    return counts


def _span_payload(span: SyllabusSpan | None) -> dict[str, int] | None:
    if span is None:
        return None
    return {
        "start_char": int(span.start_char),
        "end_char": int(span.end_char),
    }


def main() -> None:
    args = build_parser().parse_args()
    config = OntologyConfig.from_env()

    vault_root = args.vault_root or config.vault_root
    _ensure_vault_structure(vault_root)

    input_text = _read_input_text(args.text_file)
    full_citation_mentions = extract_citation_mentions(input_text) if input_text else []
    full_authority_mentions = extract_authority_mentions(input_text) if input_text else []
    citation_mentions, citation_anchor_scope, citation_syllabus_span = (
        extract_citation_mentions_syllabus_first(
            input_text,
            full_mentions=full_citation_mentions,
            min_mentions_for_syllabus=SYLLABUS_CITATION_MIN_MENTIONS,
        )
        if input_text
        else ([], "full_opinion_empty", None)
    )
    authority_mentions, authority_anchor_scope, authority_syllabus_span = (
        extract_authority_mentions_syllabus_first(
            input_text,
            full_mentions=full_authority_mentions,
            min_mentions_for_syllabus=SYLLABUS_AUTHORITY_MIN_MENTIONS,
        )
        if input_text
        else ([], "full_opinion_empty", None)
    )
    role_assignments = classify_citation_roles(input_text, full_citation_mentions) if input_text and full_citation_mentions else []

    manual_citations = [c for c in args.citation if c and c.strip()]
    mention_citations = [m.normalized_text for m in full_citation_mentions]
    all_citations = sorted(set(mention_citations + manual_citations))

    resolved = []
    if all_citations and not args.skip_resolver and config.resolver_enabled:
        resolver = CitationResolver(
            lookup_url=config.courtlistener_citation_lookup_url,
            api_token=config.courtlistener_api_token,
            cache_path=config.citation_cache_path,
            request_timeout=config.request_timeout_seconds,
        )
        resolved = resolver.resolve_many(all_citations)

    resolved_case_map = {item.normalized_citation: item.resolved_case_id for item in resolved}
    resolved_confidence_map = {item.normalized_citation: float(item.confidence) for item in resolved}
    citation_role_map = _build_citation_role_map(role_assignments)

    extraction = None
    extraction_error: str | None = None
    if args.extraction_json:
        extraction = parse_extraction_json(args.extraction_json.read_text(encoding="utf-8"))
    elif args.run_extractor and input_text:
        try:
            extraction = extract_structures(
                opinion_text=input_text,
                resolved_citations=[item.__dict__ for item in resolved],
            )
        except Exception as exc:
            extraction_error = str(exc)

    provisional_title = _default_title(args, args.text_file)
    provisional_primary_citation = args.primary_citation or (all_citations[0] if all_citations else "unknown")
    legacy_case_id = build_case_id(
            jurisdiction=args.jurisdiction,
            court=args.court,
            date_decided=args.date_decided,
            title=provisional_title,
            primary_citation=provisional_primary_citation,
        )
    provisional_case_id = str(args.case_id or "").strip() or legacy_case_id
    primary_citation = provisional_primary_citation
    normalized_primary = normalize_citation(primary_citation)
    if normalized_primary:
        resolved_case_map.setdefault(normalized_primary, provisional_case_id)
        resolved_confidence_map.setdefault(normalized_primary, 1.0)

    writer = VaultWriter(vault_root=vault_root)
    local_case_citation_map = writer.load_existing_case_citation_map()
    resolved_case_map = _merge_local_case_resolution(all_citations, resolved_case_map, local_case_citation_map)
    resolved_case_map = _remap_resolver_results_to_local_case_ids(
        resolved_items=resolved,
        resolved_case_map=resolved_case_map,
        local_case_citation_map=local_case_citation_map,
    )
    params = load_params(args.params_file)
    citation_anchors = _build_case_citation_anchors(
        mentions=citation_mentions,
        resolved_case_map=resolved_case_map,
        citation_role_map=citation_role_map,
        case_id=provisional_case_id,
        resolver_confidence_map=resolved_confidence_map,
    )
    if citation_anchor_scope == "syllabus" and not citation_anchors and full_citation_mentions:
        citation_anchors = _build_case_citation_anchors(
            mentions=full_citation_mentions,
            resolved_case_map=resolved_case_map,
            citation_role_map=citation_role_map,
            case_id=provisional_case_id,
            resolver_confidence_map=resolved_confidence_map,
        )
        citation_anchor_scope = "full_opinion_fallback_no_citation_anchor"
        citation_mentions = full_citation_mentions
    authority_anchors = _build_case_authority_anchors(authority_mentions)
    if authority_anchor_scope == "syllabus" and not authority_anchors and full_authority_mentions:
        authority_anchors = _build_case_authority_anchors(full_authority_mentions)
        authority_anchor_scope = "full_opinion_fallback_no_authority_anchor"
        authority_mentions = full_authority_mentions
    interpretive_edges, interpretive_source_nodes, interpretive_unresolved = _build_interpretive_edges(
        extraction=extraction,
        case_id=provisional_case_id,
        authority_anchors=authority_anchors,
        resolved_case_map=resolved_case_map,
        params=params,
    )
    case_node = _build_case_node(
        args=args,
        all_citations=all_citations,
        text_file=args.text_file,
        opinion_text=input_text,
        extraction=extraction,
        citation_anchors=citation_anchors,
        authority_anchors=authority_anchors,
        interpretive_edges=interpretive_edges,
    )
    if legacy_case_id and legacy_case_id != case_node.case_id:
        case_node.sources["legacy_case_id"] = legacy_case_id
    if args.case_id:
        case_node.sources["manifest_case_id"] = str(args.case_id or "").strip()

    taxonomy_root = Path(__file__).resolve().parents[1] / "taxonomy" / "2026.01"
    taxonomy_nodes = map_case_taxonomies(
        title=case_node.title,
        case_summary=case_node.case_summary,
        essential_holding=case_node.essential_holding,
        opinion_text=input_text,
        taxonomy_path=taxonomy_root / "taxonomy.yaml",
        aliases_path=taxonomy_root / "aliases.yaml",
        max_results=12,
    )
    case_node.case_taxonomies = taxonomy_nodes
    if case_node.case_id != provisional_case_id:
        normalized_primary = normalize_citation(primary_citation)
        if normalized_primary:
            resolved_case_map[normalized_primary] = case_node.case_id
        for edge in interpretive_edges:
            edge["source_case"] = case_node.case_id
        case_node.interpretive_edges = interpretive_edges
    case_node.sources["anchor_citation_scope"] = citation_anchor_scope
    case_node.sources["anchor_authority_scope"] = authority_anchor_scope
    anchor_span = citation_syllabus_span or authority_syllabus_span
    span_payload = _span_payload(anchor_span)
    if span_payload:
        case_node.sources["anchor_syllabus_span"] = span_payload

    holding_nodes = _build_holding_nodes(case_node, extraction, resolved_case_map) if extraction else []
    source_nodes, holding_nodes = _build_source_nodes_and_link_holdings(holding_nodes, extraction, params)
    authority_source_nodes = _build_source_nodes_from_authority_anchors(authority_anchors, params)
    source_nodes = _merge_source_nodes(source_nodes, authority_source_nodes)
    source_nodes = _merge_source_nodes(source_nodes, interpretive_source_nodes)

    existing_issues = writer.load_existing_issues()
    relation_citation_mentions = _build_relation_citation_mentions(full_citation_mentions, citation_role_map, resolved_case_map)
    canonicalization = canonicalize_issues(
        extracted_issues=extraction.issues if extraction else [],
        citation_case_map=resolved_case_map,
        existing_issues=existing_issues,
        default_linked_holdings=[item.holding_id for item in holding_nodes],
        citation_role_map=citation_role_map,
    )
    existing_holding_ids = writer.load_existing_holding_ids()
    known_holding_ids = set(existing_holding_ids).union({item.holding_id for item in holding_nodes})

    relation_result = build_relation_nodes(
        extracted_relations=extraction.relations if extraction else [],
        holding_ids=[item.holding_id for item in holding_nodes],
        opinion_text=input_text,
        known_holding_ids=known_holding_ids,
        citation_mentions=relation_citation_mentions,
    )

    metrics_bundle = apply_metrics(
        holdings=holding_nodes,
        issues=canonicalization.issues,
        relations=relation_result.relations,
        params=params,
    )

    unresolved_items: list[dict] = []
    for item in resolved:
        if not item.resolved_case_id or item.confidence < 0.7:
            unresolved_items.append(
                {
                    "type": "citation_unresolved",
                    "reason": "no_resolution" if not item.resolved_case_id else "low_confidence",
                    "normalized_citation": item.normalized_citation,
                    "confidence": item.confidence,
                }
            )
    unresolved_items.extend(interpretive_unresolved)
    unresolved_items.extend(canonicalization.unresolved)
    unresolved_items.extend(relation_result.unresolved)
    if extraction_error:
        unresolved_items.append(
            {
                "type": "extraction_unresolved",
                "reason": "extractor_failed",
                "detail": extraction_error,
            }
        )
    unresolved_items = _enrich_unresolved_items(unresolved_items)
    unresolved_by_severity = _count_unresolved_by_severity(unresolved_items)

    metrics_payload = {
        **metrics_bundle.summary,
        "explainability": metrics_bundle.explainability,
    }
    interpretation_events = list(metrics_bundle.interpretation_events or [])
    interpretation_events.extend(_interpretive_events_from_edges(interpretive_edges))

    write_result = None
    if not args.dry_run:
        write_result = writer.write_all(
            case_node=case_node,
            holding_nodes=holding_nodes,
            issue_nodes=canonicalization.issues,
            relation_nodes=relation_result.relations,
            source_nodes=source_nodes,
            unresolved_items=unresolved_items,
            params=params,
            metrics_payload=metrics_payload,
            explainability_payload=metrics_bundle.explainability,
            interpretation_events=interpretation_events,
        )

    payload = {
        "vault_root": str(vault_root),
        "text_file": str(args.text_file) if args.text_file else None,
        "citation_count": len(all_citations),
        "citations": all_citations,
        "mentions": [m.__dict__ for m in citation_mentions],
        "mentions_full": [m.__dict__ for m in full_citation_mentions],
        "authority_mentions": [m.__dict__ for m in authority_mentions],
        "authority_mentions_full": [m.__dict__ for m in full_authority_mentions],
        "anchor_citation_scope": citation_anchor_scope,
        "anchor_authority_scope": authority_anchor_scope,
        "anchor_syllabus_span": _span_payload(citation_syllabus_span or authority_syllabus_span),
        "citation_roles": [
            {
                "normalized_text": item.mention.normalized_text,
                "role": item.role.value,
                "confidence": item.confidence,
            }
            for item in role_assignments
        ],
        "resolved": [item.__dict__ for item in resolved],
        "extraction_error": extraction_error,
        "case_id": case_node.case_id,
        "case_summary": case_node.case_summary,
        "essential_holding": case_node.essential_holding,
        "citation_anchor_count": len(case_node.citation_anchors or []),
        "authority_anchor_count": len(case_node.authority_anchors or []),
        "interpretive_edge_count": len(case_node.interpretive_edges or []),
        "holding_count": len(holding_nodes),
        "issue_count": len(canonicalization.issues),
        "relation_count": len(relation_result.relations),
        "source_count": len(source_nodes),
        "unresolved_count": len(unresolved_items),
        "unresolved_by_severity": unresolved_by_severity,
        "unresolved_items": unresolved_items,
        "metrics_summary": metrics_bundle.summary,
        "metrics_explainability": metrics_bundle.explainability,
        "interpretive_edges": case_node.interpretive_edges,
        "canonicalization_decisions": [
            {
                "source_index": decision.source_index,
                "issue_id": decision.issue_id,
                "created": decision.created,
                "score": decision.score,
                "reason": decision.reason,
            }
            for decision in canonicalization.decisions
        ],
        "write_result": write_result,
    }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
