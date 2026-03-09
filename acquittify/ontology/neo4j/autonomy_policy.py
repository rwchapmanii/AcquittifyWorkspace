from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
import yaml


class HardInvariantThresholds(BaseModel):
    model_config = ConfigDict(extra="ignore")

    shape_pass_rate_min_gold: float = 1.0
    shape_pass_rate_min_release_gate: float | None = None
    temporal_leakage_max: float = 0.0
    duplicate_entity_rate_max: float = 0.0
    merge_collision_rate_max: float = 0.0
    namespace_reference_required: bool = True
    ontology_version_reference_required: bool = True


class Thresholds(BaseModel):
    model_config = ConfigDict(extra="ignore")

    hard_invariants: HardInvariantThresholds = Field(default_factory=HardInvariantThresholds)


class AutonomyPolicy(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: int | str
    policy_id: str
    policy_name: str | None = None
    status: str | None = None
    thresholds: Thresholds = Field(default_factory=Thresholds)
    hard_vetoes: list[str] = Field(default_factory=list)


class ValidationMetrics(BaseModel):
    model_config = ConfigDict(extra="ignore")

    shape_pass_rate_gold: float | None = None
    temporal_leakage_rate: float | None = None
    duplicate_entity_rate: float | None = None
    merge_collision_rate: float | None = None
    namespace_reference_present_rate: float | None = None
    ontology_version_reference_present_rate: float | None = None


class AutonomyDecision(BaseModel):
    decision: str
    policy_id: str
    hard_vetoes_triggered: list[str] = Field(default_factory=list)
    failed_checks: list[str] = Field(default_factory=list)
    summary: str


def load_autonomy_policy(path: Path) -> AutonomyPolicy:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Autonomy policy must be a YAML object")
    return AutonomyPolicy.model_validate(payload)


def evaluate_autonomy_policy(policy: AutonomyPolicy, metrics: ValidationMetrics) -> AutonomyDecision:
    thresholds = policy.thresholds.hard_invariants
    failed_checks: list[str] = []
    vetoes: list[str] = []

    if metrics.shape_pass_rate_gold is None:
        failed_checks.append("missing_metric:shape_pass_rate_gold")
    elif metrics.shape_pass_rate_gold < thresholds.shape_pass_rate_min_gold:
        failed_checks.append(
            f"shape_pass_rate_gold<{thresholds.shape_pass_rate_min_gold:.4f}"
        )
        vetoes.append("shape_pass_rate_below_minimum")

    if metrics.temporal_leakage_rate is None:
        failed_checks.append("missing_metric:temporal_leakage_rate")
    elif metrics.temporal_leakage_rate > thresholds.temporal_leakage_max:
        failed_checks.append(
            f"temporal_leakage_rate>{thresholds.temporal_leakage_max:.4f}"
        )
        vetoes.append("temporal_leakage_detected")

    if metrics.duplicate_entity_rate is None:
        failed_checks.append("missing_metric:duplicate_entity_rate")
    elif metrics.duplicate_entity_rate > thresholds.duplicate_entity_rate_max:
        failed_checks.append(
            f"duplicate_entity_rate>{thresholds.duplicate_entity_rate_max:.4f}"
        )

    if metrics.merge_collision_rate is None:
        failed_checks.append("missing_metric:merge_collision_rate")
    elif metrics.merge_collision_rate > thresholds.merge_collision_rate_max:
        failed_checks.append(
            f"merge_collision_rate>{thresholds.merge_collision_rate_max:.4f}"
        )

    if thresholds.namespace_reference_required:
        if metrics.namespace_reference_present_rate is None:
            failed_checks.append("missing_metric:namespace_reference_present_rate")
        elif metrics.namespace_reference_present_rate < 1.0:
            failed_checks.append("namespace_reference_present_rate<1.0")

    if thresholds.ontology_version_reference_required:
        if metrics.ontology_version_reference_present_rate is None:
            failed_checks.append("missing_metric:ontology_version_reference_present_rate")
        elif metrics.ontology_version_reference_present_rate < 1.0:
            failed_checks.append("ontology_version_reference_present_rate<1.0")

    # Any missing metric in hard invariants forces reject in v1_strict.
    if any(check.startswith("missing_metric:") for check in failed_checks):
        vetoes.append("missing_required_hard_invariant_metric")

    # Filter vetoes to policy-known labels when provided.
    if policy.hard_vetoes:
        filtered = [veto for veto in vetoes if veto in set(policy.hard_vetoes)]
        if filtered:
            vetoes = filtered

    decision = "promote_stage_or_reject"
    if vetoes or failed_checks:
        decision = "reject"

    summary = "hard invariants passed"
    if decision == "reject":
        summary = "hard invariant checks failed"

    return AutonomyDecision(
        decision=decision,
        policy_id=policy.policy_id,
        hard_vetoes_triggered=sorted(set(vetoes)),
        failed_checks=sorted(set(failed_checks)),
        summary=summary,
    )


def metrics_from_validation_report(report: dict[str, Any]) -> ValidationMetrics:
    files_scanned = float(report.get("files_scanned") or 0.0)
    valid_files = float(report.get("valid_files") or 0.0)
    valid_rate = float(report.get("valid_rate") or 0.0) if files_scanned > 0 else 0.0

    duplicate_entity_rate = report.get("duplicate_case_id_rate")
    if duplicate_entity_rate is None:
        duplicate_entity_rate = 0.0 if files_scanned > 0 else None

    namespace_rate = report.get("namespace_reference_present_rate")
    ontology_rate = report.get("ontology_version_reference_present_rate")

    return ValidationMetrics(
        shape_pass_rate_gold=valid_rate,
        temporal_leakage_rate=report.get("temporal_leakage_rate"),
        duplicate_entity_rate=duplicate_entity_rate,
        merge_collision_rate=report.get("merge_collision_rate"),
        namespace_reference_present_rate=namespace_rate,
        ontology_version_reference_present_rate=ontology_rate,
    )
