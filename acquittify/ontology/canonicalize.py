from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re

from acquittify.metadata_extract import normalize_citation

from .ids import build_issue_id, stable_hash
from .schemas import IssueNode


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_DIMENSION_CANONICAL_ALIASES = {
    "vehicle_status": "vehicle_status",
    "vehicle_mobility": "vehicle_status",
    "mobility_status": "vehicle_status",
    "custody_status": "custody_status",
    "impound_status": "custody_status",
    "container_status": "container_scope",
    "container_scope": "container_scope",
    "probable_cause_status": "probable_cause_status",
}
_DIMENSION_HINTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bimpound(?:ed|ment)?\b", re.IGNORECASE), "custody_status"),
    (re.compile(r"\bimmobiliz(?:e|ed|ation)\b", re.IGNORECASE), "custody_status"),
    (re.compile(r"\btow(?:ed|ing)?\b", re.IGNORECASE), "custody_status"),
    (re.compile(r"\bcustody\b", re.IGNORECASE), "custody_status"),
    (re.compile(r"\bvehicle\b|\bautomobile\b|\bcar\b|\btruck\b", re.IGNORECASE), "vehicle_status"),
    (re.compile(r"\bcontainer\b|\bpackage\b|\btrunk\b", re.IGNORECASE), "container_scope"),
    (re.compile(r"\bprobable cause\b", re.IGNORECASE), "probable_cause_status"),
]
_GENERIC_RULE_TYPES = {"", "unknown", "general", "unspecified"}


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall((text or "").lower()))


def _jaccard(a: str, b: str) -> float:
    a_tokens = _tokens(a)
    b_tokens = _tokens(b)
    if not a_tokens and not b_tokens:
        return 0.0
    denom = len(a_tokens.union(b_tokens))
    if denom == 0:
        return 0.0
    return len(a_tokens.intersection(b_tokens)) / denom


def _slug_token(text: str) -> str:
    ordered: list[str] = []
    seen: set[str] = set()
    for token in _TOKEN_RE.findall((text or "").lower()):
        if token in seen:
            continue
        seen.add(token)
        ordered.append(token)
    return "_".join(ordered)


def _normalize_dimension_name(raw: str) -> str:
    token = _slug_token(raw)
    if not token:
        return ""
    return _DIMENSION_CANONICAL_ALIASES.get(token, token)


def _infer_dimensions_from_text(text: str) -> set[str]:
    inferred: set[str] = set()
    for pattern, dimension in _DIMENSION_HINTS:
        if pattern.search(text or ""):
            inferred.add(dimension)
    return inferred


def _issue_dimensions(extracted_issue) -> set[str]:
    dimensions: set[str] = set()
    for raw in extracted_issue.required_fact_dimensions or []:
        normalized = _normalize_dimension_name(str(raw))
        if normalized:
            dimensions.add(normalized)
    dimensions.update(_infer_dimensions_from_text(extracted_issue.normalized_form or ""))
    return dimensions


def _existing_issue_dimensions(issue: IssueNode) -> set[str]:
    values = (issue.dimensions or {}).get("required_fact_dimensions", []) or []
    normalized: set[str] = set()
    for raw in values:
        item = _normalize_dimension_name(str(raw))
        if item:
            normalized.add(item)
    return normalized


def _merge_issue_dimensions(existing: IssueNode, extracted_dimensions: set[str]) -> dict[str, list[str]]:
    merged = _existing_issue_dimensions(existing).union(extracted_dimensions)
    return {"required_fact_dimensions": sorted(merged)}


def _taxonomy_token(value: str | None) -> str:
    return _slug_token(value or "")


def _matches_dimension_first_rule(extracted_issue, candidate: IssueNode) -> bool:
    extracted_taxonomy = extracted_issue.taxonomy or {}
    candidate_taxonomy = candidate.taxonomy or {}

    extracted_domain = _taxonomy_token(extracted_taxonomy.get("domain"))
    extracted_doctrine = _taxonomy_token(extracted_taxonomy.get("doctrine"))
    extracted_rule_type = _taxonomy_token(extracted_taxonomy.get("rule_type"))
    candidate_domain = _taxonomy_token(candidate_taxonomy.get("domain"))
    candidate_doctrine = _taxonomy_token(candidate_taxonomy.get("doctrine"))
    candidate_rule_type = _taxonomy_token(candidate_taxonomy.get("rule_type"))

    if not extracted_domain or not extracted_doctrine:
        return False
    if extracted_domain != candidate_domain or extracted_doctrine != candidate_doctrine:
        return False

    if extracted_rule_type not in _GENERIC_RULE_TYPES and extracted_rule_type != candidate_rule_type:
        return False
    return True


@dataclass(frozen=True)
class CanonicalizationDecision:
    source_index: int
    issue_id: str | None
    created: bool
    score: float
    reason: str


@dataclass(frozen=True)
class CanonicalizationOutcome:
    issues: list[IssueNode]
    decisions: list[CanonicalizationDecision]
    unresolved: list[dict]


def load_issue_index(issue_index_path: Path) -> list[IssueNode]:
    if not issue_index_path.exists():
        return []
    try:
        payload = json.loads(issue_index_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    items = payload if isinstance(payload, list) else payload.get("issues", []) if isinstance(payload, dict) else []
    nodes: list[IssueNode] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            nodes.append(IssueNode(**item))
        except Exception:
            continue
    return nodes


def _support_case_ids(supporting_citations: list[str], citation_case_map: dict[str, str | None]) -> set[str]:
    case_ids: set[str] = set()
    for citation in supporting_citations:
        normalized = normalize_citation(citation)
        resolved = citation_case_map.get(normalized)
        if resolved:
            case_ids.add(resolved)
    return case_ids


def _support_case_ids_preferring_controlling(
    supporting_citations: list[str],
    citation_case_map: dict[str, str | None],
    citation_role_map: dict[str, str] | None,
) -> set[str]:
    if not citation_role_map:
        return _support_case_ids(supporting_citations, citation_case_map)

    controlling_case_ids: set[str] = set()
    all_case_ids: set[str] = set()
    for citation in supporting_citations:
        normalized = normalize_citation(citation)
        resolved = citation_case_map.get(normalized)
        if not resolved:
            continue
        all_case_ids.add(resolved)
        role = citation_role_map.get(normalized)
        if role == "controlling":
            controlling_case_ids.add(resolved)

    return controlling_case_ids if controlling_case_ids else all_case_ids


def _issue_score(
    extracted_issue,
    existing_issue: IssueNode,
    citation_case_ids: set[str],
    extracted_dimensions: set[str],
) -> tuple[float, str]:
    score = 0.0
    reasons: list[str] = []

    existing_anchor_ids = set(existing_issue.anchors.get("canonical_citations", []) or [])
    overlap = citation_case_ids.intersection(existing_anchor_ids)
    if overlap:
        score += 6.0
        reasons.append("citation_root")

    extracted_taxonomy = extracted_issue.taxonomy or {}
    existing_taxonomy = existing_issue.taxonomy or {}

    if extracted_taxonomy.get("domain") and extracted_taxonomy.get("domain") == existing_taxonomy.get("domain"):
        score += 1.5
        reasons.append("domain")
    if extracted_taxonomy.get("doctrine") and extracted_taxonomy.get("doctrine") == existing_taxonomy.get("doctrine"):
        score += 2.0
        reasons.append("doctrine")
    if extracted_taxonomy.get("rule_type") and extracted_taxonomy.get("rule_type") == existing_taxonomy.get("rule_type"):
        score += 2.0
        reasons.append("rule_type")

    semantic = _jaccard(extracted_issue.normalized_form, existing_issue.normalized_form)
    if semantic >= 0.25:
        score += semantic * 2.0
        reasons.append("semantic")

    existing_dimensions = _existing_issue_dimensions(existing_issue)
    if extracted_dimensions and existing_dimensions:
        overlap = extracted_dimensions.intersection(existing_dimensions)
        if overlap:
            score += 1.0
            reasons.append("dimension_overlap")

    reason = "+".join(reasons) if reasons else "no_match"
    return score, reason


def _minimality_ok(extracted_issue) -> tuple[bool, str]:
    signals = 0
    supporting = extracted_issue.supporting_citations or []
    if supporting:
        signals += 1

    taxonomy = extracted_issue.taxonomy or {}
    taxonomy_signals = sum(1 for key in ("domain", "doctrine", "rule_type") if taxonomy.get(key))
    if taxonomy_signals >= 2:
        signals += 1

    norm = (extracted_issue.normalized_form or "").strip()
    if norm.lower().startswith("whether") or "?" in norm:
        signals += 1

    if signals >= 2:
        return True, "ok"
    return False, "minimality_reject"


def _build_new_issue_id(extracted_issue, existing_ids: set[str]) -> str:
    taxonomy = extracted_issue.taxonomy or {}
    base = build_issue_id(
        taxonomy.get("domain") or "unknown",
        taxonomy.get("doctrine") or "unspecified",
        taxonomy.get("rule_type") or "general",
    )
    if base not in existing_ids:
        return base

    suffix = stable_hash(extracted_issue.normalized_form, size=8)
    candidate = f"{base}.{suffix}"
    if candidate not in existing_ids:
        return candidate

    idx = 2
    while f"{candidate}.{idx}" in existing_ids:
        idx += 1
    return f"{candidate}.{idx}"


def canonicalize_issues(
    extracted_issues: list,
    citation_case_map: dict[str, str | None],
    existing_issues: list[IssueNode],
    *,
    default_linked_holdings: list[str] | None = None,
    citation_role_map: dict[str, str] | None = None,
    match_threshold: float = 5.0,
) -> CanonicalizationOutcome:
    by_id = {issue.issue_id: issue for issue in existing_issues}
    unresolved: list[dict] = []
    decisions: list[CanonicalizationDecision] = []

    existing_ids = set(by_id.keys())

    for idx, extracted_issue in enumerate(extracted_issues):
        ok, minimality_reason = _minimality_ok(extracted_issue)
        if not ok:
            unresolved.append(
                {
                    "type": "issue_unresolved",
                    "source_index": idx,
                    "reason": minimality_reason,
                    "normalized_form": extracted_issue.normalized_form,
                }
            )
            decisions.append(
                CanonicalizationDecision(
                    source_index=idx,
                    issue_id=None,
                    created=False,
                    score=0.0,
                    reason=minimality_reason,
                )
            )
            continue

        citation_case_ids = _support_case_ids_preferring_controlling(
            extracted_issue.supporting_citations or [],
            citation_case_map,
            citation_role_map,
        )
        extracted_dimensions = _issue_dimensions(extracted_issue)

        best_issue_id: str | None = None
        best_score = -1.0
        best_reason = "no_match"

        for existing in by_id.values():
            score, reason = _issue_score(extracted_issue, existing, citation_case_ids, extracted_dimensions)
            if score > best_score:
                best_score = score
                best_issue_id = existing.issue_id
                best_reason = reason

        if best_issue_id and best_score >= match_threshold:
            current = by_id[best_issue_id]
            linked_holdings = sorted(set(current.linked_holdings).union(default_linked_holdings or []))
            canonical_citations = sorted(
                set(current.anchors.get("canonical_citations", [])).union(citation_case_ids)
            )

            updated = IssueNode(
                issue_id=current.issue_id,
                normalized_form=current.normalized_form,
                taxonomy=current.taxonomy,
                anchors={
                    **current.anchors,
                    "canonical_citations": canonical_citations,
                },
                dimensions=_merge_issue_dimensions(current, extracted_dimensions),
                linked_holdings=linked_holdings,
                metrics=current.metrics,
            )
            by_id[current.issue_id] = updated
            decisions.append(
                CanonicalizationDecision(
                    source_index=idx,
                    issue_id=current.issue_id,
                    created=False,
                    score=best_score,
                    reason=best_reason,
                )
            )
            continue

        dimension_first_issue_id = None
        for existing in by_id.values():
            if _matches_dimension_first_rule(extracted_issue, existing):
                dimension_first_issue_id = existing.issue_id
                break
        if dimension_first_issue_id:
            current = by_id[dimension_first_issue_id]
            linked_holdings = sorted(set(current.linked_holdings).union(default_linked_holdings or []))
            canonical_citations = sorted(
                set(current.anchors.get("canonical_citations", [])).union(citation_case_ids)
            )
            updated = IssueNode(
                issue_id=current.issue_id,
                normalized_form=current.normalized_form,
                taxonomy=current.taxonomy,
                anchors={
                    **current.anchors,
                    "canonical_citations": canonical_citations,
                },
                dimensions=_merge_issue_dimensions(current, extracted_dimensions),
                linked_holdings=linked_holdings,
                metrics=current.metrics,
            )
            by_id[current.issue_id] = updated
            decisions.append(
                CanonicalizationDecision(
                    source_index=idx,
                    issue_id=current.issue_id,
                    created=False,
                    score=best_score if best_score > 0 else 0.0,
                    reason="dimension_first_attach",
                )
            )
            continue

        new_issue_id = _build_new_issue_id(extracted_issue, existing_ids)
        existing_ids.add(new_issue_id)

        taxonomy = extracted_issue.taxonomy or {}
        new_issue = IssueNode(
            issue_id=new_issue_id,
            normalized_form=extracted_issue.normalized_form,
            taxonomy={
                "domain": taxonomy.get("domain", "Unknown"),
                "subdomain": taxonomy.get("subdomain", "Unknown"),
                "doctrine": taxonomy.get("doctrine", "Unknown"),
                "rule_type": taxonomy.get("rule_type", "General"),
            },
            anchors={
                "canonical_citations": sorted(citation_case_ids),
            },
            dimensions={"required_fact_dimensions": sorted(extracted_dimensions)},
            linked_holdings=sorted(set(default_linked_holdings or [])),
            metrics={"PF_issue": None, "consensus": None, "drift": None, "last_updated": None},
        )
        by_id[new_issue_id] = new_issue

        decisions.append(
            CanonicalizationDecision(
                source_index=idx,
                issue_id=new_issue_id,
                created=True,
                score=best_score if best_score > 0 else 0.0,
                reason="created_new",
            )
        )

    merged = sorted(by_id.values(), key=lambda item: item.issue_id)
    return CanonicalizationOutcome(issues=merged, decisions=decisions, unresolved=unresolved)
