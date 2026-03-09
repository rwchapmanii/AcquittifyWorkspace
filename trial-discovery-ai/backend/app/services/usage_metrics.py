from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models.user_account_metric import UserAccountMetric
from app.db.models.user_metric_event import UserMetricEvent


def record_login_success(
    *,
    session: Session,
    user_id: UUID,
    organization_id: UUID,
) -> None:
    now_utc = datetime.now(timezone.utc)
    metric = _ensure_metric(
        session=session,
        user_id=user_id,
        organization_id=organization_id,
    )
    metric.total_logins += 1
    metric.last_login_at = now_utc
    metric.last_activity_at = now_utc
    metric.updated_at = now_utc
    _record_event(
        session=session,
        user_id=user_id,
        organization_id=organization_id,
        event_type="login_success",
        quantity=1,
        metadata_json=None,
    )


def record_password_reset(
    *,
    session: Session,
    user_id: UUID,
    organization_id: UUID,
) -> None:
    now_utc = datetime.now(timezone.utc)
    metric = _ensure_metric(
        session=session,
        user_id=user_id,
        organization_id=organization_id,
    )
    metric.total_password_resets += 1
    metric.last_activity_at = now_utc
    metric.updated_at = now_utc
    _record_event(
        session=session,
        user_id=user_id,
        organization_id=organization_id,
        event_type="password_reset",
        quantity=1,
        metadata_json=None,
    )


def record_document_upload(
    *,
    session: Session,
    user_id: UUID,
    organization_id: UUID,
    matter_id: UUID,
    document_id: UUID,
    file_size: int,
    original_filename: str,
) -> None:
    now_utc = datetime.now(timezone.utc)
    size = max(0, int(file_size))
    metric = _ensure_metric(
        session=session,
        user_id=user_id,
        organization_id=organization_id,
    )
    metric.total_documents += 1
    metric.total_upload_bytes += size
    metric.total_storage_bytes += size
    metric.last_activity_at = now_utc
    metric.updated_at = now_utc
    _record_event(
        session=session,
        user_id=user_id,
        organization_id=organization_id,
        matter_id=matter_id,
        document_id=document_id,
        event_type="document_upload",
        quantity=size,
        metadata_json={"filename": original_filename, "bytes": size},
    )


def record_agent_usage(
    *,
    session: Session,
    user_id: UUID,
    organization_id: UUID,
    matter_id: UUID,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    model: str | None,
    used_search_fallback: bool,
) -> None:
    now_utc = datetime.now(timezone.utc)
    prompt = max(0, int(prompt_tokens))
    completion = max(0, int(completion_tokens))
    total = max(0, int(total_tokens))
    metric = _ensure_metric(
        session=session,
        user_id=user_id,
        organization_id=organization_id,
    )
    metric.total_agent_requests += 1
    metric.total_agent_prompt_tokens += prompt
    metric.total_agent_completion_tokens += completion
    metric.total_agent_tokens += total
    metric.last_activity_at = now_utc
    metric.updated_at = now_utc
    _record_event(
        session=session,
        user_id=user_id,
        organization_id=organization_id,
        matter_id=matter_id,
        event_type="agent_request",
        quantity=total,
        metadata_json={
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
            "model": model,
            "used_search_fallback": used_search_fallback,
        },
    )


def _ensure_metric(
    *,
    session: Session,
    user_id: UUID,
    organization_id: UUID,
) -> UserAccountMetric:
    metric = session.get(UserAccountMetric, user_id)
    if metric is None:
        metric = UserAccountMetric(
            user_id=user_id,
            organization_id=organization_id,
            total_storage_bytes=0,
            total_upload_bytes=0,
            total_documents=0,
            total_agent_requests=0,
            total_agent_prompt_tokens=0,
            total_agent_completion_tokens=0,
            total_agent_tokens=0,
            total_logins=0,
            total_password_resets=0,
        )
        session.add(metric)
        session.flush()
    elif metric.organization_id != organization_id:
        metric.organization_id = organization_id
    return metric


def _record_event(
    *,
    session: Session,
    user_id: UUID,
    organization_id: UUID,
    event_type: str,
    quantity: int,
    metadata_json: dict | None,
    matter_id: UUID | None = None,
    document_id: UUID | None = None,
) -> None:
    session.add(
        UserMetricEvent(
            user_id=user_id,
            organization_id=organization_id,
            matter_id=matter_id,
            document_id=document_id,
            event_type=event_type,
            quantity=max(0, int(quantity)),
            metadata_json=metadata_json,
        )
    )
