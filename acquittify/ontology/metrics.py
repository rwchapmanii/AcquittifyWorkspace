from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from math import log
from pathlib import Path
import json
import re

from .schemas import HoldingNode, IssueNode, RelationNode, RelationType


DEFAULT_PARAMS: dict = {
    "authority_weights": {
        "supreme": 1.0,
        "in_circuit_en_banc": 0.9,
        "in_circuit_panel": 0.8,
        "out_of_circuit_panel": 0.7,
        "in_circuit_district": 0.5,
        "out_of_circuit_district": 0.4,
        "secondary": 0.3,
    },
    "publication_multiplier": {
        "published": 1.0,
        "unpublished": 0.75,
        "nonprecedential": 0.6,
    },
    "majority_multiplier": {
        "majority": 1.0,
        "plurality": 0.85,
        "concurrence_only": 0.6,
    },
    "citation_type_multiplier": {
        "controlling": 1.0,
        "persuasive": 0.6,
        "background": 0.35,
    },
    "relation_effects": {
        "applies": 0.06,
        "clarifies": 0.05,
        "extends": 0.04,
        "distinguishes": -0.05,
        "limits": -0.10,
        "overrules": -0.90,
        "questions": -0.15,
    },
    "issue_adjustments": {
        "consensus_gamma": 0.35,
        "drift_delta": 0.45,
    },
    "source_type_multiplier": {
        "constitution": 1.0,
        "statute": 0.95,
        "reg": 0.9,
        "secondary": 0.3,
        "other": 0.85,
    },
}


@dataclass(frozen=True)
class MetricsBundle:
    holding_scores: dict[str, float]
    issue_scores: dict[str, dict]
    interpretation_events: list[dict]
    summary: dict
    explainability: dict


def _parse_scalar(value: str):
    text = value.strip()
    if not text:
        return ""
    if text.startswith('"') and text.endswith('"'):
        return text[1:-1]
    if text.startswith("'") and text.endswith("'"):
        return text[1:-1]
    if text.lower() == "true":
        return True
    if text.lower() == "false":
        return False
    if text.lower() == "null":
        return None
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return text


def _parse_simple_yaml(text: str) -> dict:
    root: dict = {}
    stack: list[tuple[int, dict]] = [(-1, root)]

    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip("\n\r")
        if not line.strip():
            continue

        indent = len(raw) - len(raw.lstrip(" "))
        stripped = line.strip()
        if ":" not in stripped:
            continue

        key, raw_val = stripped.split(":", 1)
        key = key.strip()
        val = raw_val.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1] if stack else root

        if not val:
            child: dict = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _parse_scalar(val)

    return root


def _deep_merge(base: dict, overlay: dict) -> dict:
    result = deepcopy(base)
    for key, value in (overlay or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_params(path: Path | None = None) -> dict:
    params = deepcopy(DEFAULT_PARAMS)
    if not path:
        return params
    if not path.exists():
        return params

    raw = path.read_text(encoding="utf-8")
    parsed = None
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = _parse_simple_yaml(raw)

    if not isinstance(parsed, dict):
        return params
    return _deep_merge(params, parsed)


def _holding_base_weight(holding: HoldingNode) -> float:
    authority = holding.authority
    if authority.final_weight and authority.final_weight > 0:
        base = float(authority.final_weight)
    else:
        base = float(authority.base_weight or 0.0)
        for value in (authority.modifiers or {}).values():
            if isinstance(value, (int, float)):
                base *= float(value)

    source_weights = [float(item.weight) for item in (holding.source_links or []) if item.weight is not None]
    if source_weights:
        base *= max(source_weights)
    return base


def _relation_effect(relation: RelationNode, params: dict) -> float:
    relation_effects = params.get("relation_effects", {}) or {}
    citation_multiplier = params.get("citation_type_multiplier", {}) or {}
    effect = float(relation_effects.get(relation.relation_type.value, 0.0))
    c_mult = float(citation_multiplier.get(relation.citation_type.value, 1.0))
    confidence = max(0.0, min(1.0, float(relation.confidence)))
    return effect * c_mult * confidence


def _compute_holding_scores(
    holdings: list[HoldingNode],
    relations: list[RelationNode],
    params: dict,
) -> tuple[dict[str, float], list[dict], dict[str, dict]]:
    by_id = {h.holding_id: h for h in holdings}
    scores = {h.holding_id: max(0.0, _holding_base_weight(h)) for h in holdings}

    incoming: dict[str, list[RelationNode]] = {h.holding_id: [] for h in holdings}
    for relation in relations:
        if relation.target_holding_id in incoming:
            incoming[relation.target_holding_id].append(relation)

    interpretation_events: list[dict] = []
    explainability: dict[str, dict] = {}
    for holding_id, rels in incoming.items():
        holding = by_id[holding_id]
        base = scores.get(holding_id, 0.0)
        delta = 0.0
        effects: list[dict] = []
        for relation in sorted(rels, key=lambda r: r.relation_id):
            effect = _relation_effect(relation, params)
            delta += effect
            effects.append(
                {
                    "relation_id": relation.relation_id,
                    "relation_type": relation.relation_type.value,
                    "source_holding_id": relation.source_holding_id,
                    "target_holding_id": relation.target_holding_id,
                    "effect": round(effect, 6),
                }
            )
            interpretation_events.append(
                {
                    "event_type": "relation_effect",
                    "relation_id": relation.relation_id,
                    "source_holding_id": relation.source_holding_id,
                    "target_holding_id": relation.target_holding_id,
                    "relation_type": relation.relation_type.value,
                    "effect": round(effect, 6),
                }
            )

        adjusted = base * (1.0 + delta)
        final_pf = round(max(0.0, adjusted), 6)
        scores[holding_id] = final_pf
        explainability[holding_id] = {
            "base_weight": round(base, 6),
            "source_links": [
                {
                    "source_id": item.source_id,
                    "weight": None if item.weight is None else float(item.weight),
                    "role": item.role,
                }
                for item in (holding.source_links or [])
            ],
            "relation_delta": round(delta, 6),
            "relation_effects": sorted(
                effects,
                key=lambda item: (-abs(float(item["effect"])), item["relation_id"]),
            ),
            "final_pf": final_pf,
        }

    # Keep deterministic order by writing back in known holdings order.
    ordered = {hid: scores.get(hid, 0.0) for hid in by_id.keys()}
    ordered_explainability = {hid: explainability.get(hid, {}) for hid in by_id.keys()}
    return ordered, interpretation_events, ordered_explainability


def _entropy_from_counts(counts: list[float]) -> float:
    total = sum(counts)
    if total <= 0:
        return 0.0
    entropy = 0.0
    for count in counts:
        if count <= 0:
            continue
        p = count / total
        entropy -= p * log(p)
    return entropy


_CIRCUIT_TOKEN_RE = re.compile(r"^(?:ca\d{1,2}|\d{1,2}(?:st|nd|rd|th)_circuit)$")


def _court_token_from_case_id(case_id: str) -> str:
    parts = (case_id or "").split(".")
    if len(parts) >= 2 and parts[1]:
        return parts[1].lower()
    return "unknown"


def _court_token_from_holding_id(holding_id: str) -> str:
    parts = (holding_id or "").split(".")
    if len(parts) >= 2 and parts[1]:
        return parts[1].lower()
    return "unknown"


def _court_bucket(token: str) -> str:
    t = (token or "unknown").lower()
    if t == "scotus":
        return "scotus"
    if _CIRCUIT_TOKEN_RE.match(t) or "circuit" in t:
        return f"circuit:{t}"
    if "district" in t:
        return f"district:{t}"
    return t


def _compute_issue_scores(
    issues: list[IssueNode],
    holdings: list[HoldingNode],
    holding_scores: dict[str, float],
    relations: list[RelationNode],
    params: dict,
) -> tuple[dict[str, dict], dict[str, dict]]:
    holding_court_bucket: dict[str, str] = {}
    for holding in holdings:
        token = _court_token_from_case_id(holding.case_id)
        holding_court_bucket[holding.holding_id] = _court_bucket(token)

    positive_types = {RelationType.applies, RelationType.clarifies, RelationType.extends}
    negative_types = {RelationType.distinguishes, RelationType.limits, RelationType.overrules, RelationType.questions}

    consensus_gamma = float((params.get("issue_adjustments", {}) or {}).get("consensus_gamma", 0.35))
    drift_delta = float((params.get("issue_adjustments", {}) or {}).get("drift_delta", 0.45))

    issue_scores: dict[str, dict] = {}
    issue_explainability: dict[str, dict] = {}
    for issue in issues:
        linked = [hid for hid in issue.linked_holdings if hid in holding_scores]
        if linked:
            mean_pf = sum(holding_scores[hid] for hid in linked) / len(linked)
        else:
            mean_pf = 0.0

        linked_set = set(linked)
        by_circuit: dict[str, dict[str, float]] = {}
        for relation in relations:
            if relation.source_holding_id not in linked_set and relation.target_holding_id not in linked_set:
                continue

            source_bucket = holding_court_bucket.get(relation.source_holding_id)
            if not source_bucket:
                source_bucket = _court_bucket(_court_token_from_holding_id(relation.source_holding_id))

            bucket_signals = by_circuit.setdefault(source_bucket, {"pos": 0.0, "neg": 0.0})
            weight = max(0.0, min(1.0, float(relation.confidence)))
            if relation.relation_type in positive_types:
                bucket_signals["pos"] += weight
            elif relation.relation_type in negative_types:
                bucket_signals["neg"] += weight

        pos = sum(values["pos"] for values in by_circuit.values())
        neg = sum(values["neg"] for values in by_circuit.values())

        total_signal = pos + neg
        if total_signal > 0:
            support_circuits = 0.0
            oppose_circuits = 0.0
            mixed_circuits = 0.0
            for values in by_circuit.values():
                pos_signal = values["pos"]
                neg_signal = values["neg"]
                if pos_signal <= 0 and neg_signal <= 0:
                    continue
                if pos_signal > neg_signal:
                    support_circuits += 1.0
                elif neg_signal > pos_signal:
                    oppose_circuits += 1.0
                else:
                    mixed_circuits += 1.0

            entropy_counts = [support_circuits, oppose_circuits, mixed_circuits]
            entropy = _entropy_from_counts(entropy_counts)
            nonzero = [value for value in entropy_counts if value > 0]
            max_entropy = log(len(nonzero)) if len(nonzero) > 1 else 0.0
            consensus = 1.0 if max_entropy <= 0 else max(0.0, 1.0 - (entropy / max_entropy))
            drift = neg / total_signal
        else:
            consensus = None
            drift = None

        adjusted = mean_pf
        consensus_multiplier = 1.0
        drift_multiplier = 1.0
        if consensus is not None:
            consensus_multiplier = 1.0 + (consensus_gamma * (consensus - 0.5))
            adjusted *= consensus_multiplier
        if drift is not None:
            drift_multiplier = 1.0 - (drift_delta * drift)
            adjusted *= drift_multiplier

        final_pf_issue = round(max(0.0, adjusted), 6)
        issue_scores[issue.issue_id] = {
            "PF_issue": final_pf_issue,
            "consensus": None if consensus is None else round(consensus, 6),
            "drift": None if drift is None else round(drift, 6),
            "active_circuits": len([1 for values in by_circuit.values() if (values["pos"] + values["neg"]) > 0]),
        }
        issue_explainability[issue.issue_id] = {
            "linked_holdings": linked,
            "mean_holding_pf": round(mean_pf, 6),
            "signal_by_circuit": {
                key: {
                    "positive": round(values["pos"], 6),
                    "negative": round(values["neg"], 6),
                }
                for key, values in sorted(by_circuit.items(), key=lambda item: item[0])
                if (values["pos"] + values["neg"]) > 0
            },
            "consensus": None if consensus is None else round(consensus, 6),
            "drift": None if drift is None else round(drift, 6),
            "consensus_multiplier": round(consensus_multiplier, 6),
            "drift_multiplier": round(drift_multiplier, 6),
            "final_pf_issue": final_pf_issue,
        }

    ordered_explainability = {issue.issue_id: issue_explainability.get(issue.issue_id, {}) for issue in issues}
    return issue_scores, ordered_explainability


def apply_metrics(
    holdings: list[HoldingNode],
    issues: list[IssueNode],
    relations: list[RelationNode],
    params: dict,
) -> MetricsBundle:
    holding_scores, interpretation_events, holding_explainability = _compute_holding_scores(holdings, relations, params)
    issue_scores, issue_explainability = _compute_issue_scores(issues, holdings, holding_scores, relations, params)

    def _model_dump(model):
        if hasattr(model, "model_dump"):
            return model.model_dump()  # type: ignore[attr-defined]
        return model.dict()

    updated_holdings: list[HoldingNode] = []
    for holding in holdings:
        score = holding_scores.get(holding.holding_id, 0.0)
        payload = _model_dump(holding)
        authority = dict(_model_dump(holding.authority))
        authority["final_weight"] = score
        payload["authority"] = authority
        payload["metrics"] = {
            **(holding.metrics or {}),
            "PF_holding": score,
        }
        updated_holdings.append(
            HoldingNode(**payload)
        )

    updated_issues: list[IssueNode] = []
    for issue in issues:
        score = issue_scores.get(issue.issue_id, {"PF_issue": 0.0, "consensus": None, "drift": None})
        payload = _model_dump(issue)
        payload["metrics"] = {
            **(issue.metrics or {}),
            **score,
        }
        updated_issues.append(
            IssueNode(**payload)
        )

    # mutate in place via list replacement semantics for caller convenience
    holdings[:] = updated_holdings
    issues[:] = updated_issues

    summary = {
        "holding_count": len(holding_scores),
        "issue_count": len(issue_scores),
        "PF_holding": holding_scores,
        "PF_issue": {k: v.get("PF_issue") for k, v in issue_scores.items()},
        "explainability_version": 1,
    }
    explainability = {
        "holdings": holding_explainability,
        "issues": issue_explainability,
        "interpretation_events": interpretation_events,
    }

    return MetricsBundle(
        holding_scores=holding_scores,
        issue_scores=issue_scores,
        interpretation_events=interpretation_events,
        summary=summary,
        explainability=explainability,
    )
