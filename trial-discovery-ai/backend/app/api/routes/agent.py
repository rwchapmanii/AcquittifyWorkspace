from fastapi import APIRouter, Depends, HTTPException
from pydantic import AliasChoices, BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import AuthContext
from app.api.authz import require_view_access, resolve_matter_for_org
from app.api.deps import get_db
from app.core.config import get_settings
from app.core.llm.client import LLMClient
from app.services.search import hybrid_search
from app.services.usage_metrics import record_agent_usage

router = APIRouter(prefix="/matters", tags=["agent"])


class AgentChatRequest(BaseModel):
    # Accept legacy payload keys and allow larger prompts (e.g., bootstrap schema context).
    message: str = Field(
        min_length=1,
        max_length=20000,
        validation_alias=AliasChoices("message", "query", "prompt", "text"),
    )
    limit: int = Field(default=6, ge=1, le=20)


def _format_hit_label(filename: str, page_num: int | None, document_id: str) -> str:
    base = filename.strip() if filename else f"Document {document_id[:8]}"
    if page_num is None:
        return base
    return f"{base} p.{page_num}"


def _build_extractive_fallback_answer(
    *,
    user_message: str,
    context_lines: list[str],
    retrieval_error: str | None,
    config_hint: str,
) -> str:
    summary_lines = []
    if context_lines:
        summary_lines.append("Search fallback answer (no LLM configured):")
        summary_lines.append("Relevant evidence excerpts:")
        summary_lines.extend(context_lines[:4])
        summary_lines.append("")
        summary_lines.append(config_hint)
    else:
        summary_lines.append(
            "No matching evidence excerpts were found for this question in the current matter."
        )
        summary_lines.append(f"Question: {user_message}")
        summary_lines.append(
            "Try narrowing by witness name, date, exhibit number, or transcript day."
        )
        summary_lines.append(config_hint)
    if retrieval_error:
        summary_lines.append("")
        summary_lines.append(
            "Retrieval warning: embeddings/vector search is not configured; lexical fallback was used."
        )
    return "\n".join(summary_lines).strip()


def _resolve_agent_model(settings: object) -> str:
    agent_model = str(getattr(settings, "agent_model", "") or "").strip()
    if agent_model:
        return agent_model
    llm_model = str(getattr(settings, "llm_model", "") or "").strip()
    return llm_model or "openclaw"


def _is_llm_configured_for_agent(settings: object, agent_model: str) -> bool:
    llm_base_url = str(getattr(settings, "llm_base_url", "") or "").strip()
    if agent_model.strip().lower() == "openclaw":
        return bool(llm_base_url)
    llm_api_key = str(getattr(settings, "llm_api_key", "") or "").strip()
    openai_api_key = str(getattr(settings, "openai_api_key", "") or "").strip()
    return bool(llm_base_url or llm_api_key or openai_api_key)


def _agent_config_hint(agent_model: str) -> str:
    if agent_model.strip().lower() == "openclaw":
        return (
            "To enable generated synthesis, configure LLM_BASE_URL for the OpenClaw "
            "gateway and set LLM_API_KEY if your gateway requires a token."
        )
    return "To enable generated synthesis, configure LLM_BASE_URL + LLM_API_KEY (or OPENAI_API_KEY)."


@router.post("/{matter_id}/agent/chat")
def chat_with_agent(
    matter_id: str,
    payload: AgentChatRequest,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_view_access),
) -> dict:
    matter = resolve_matter_for_org(
        session=session, matter_id=matter_id, organization_id=auth.organization.id
    )
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found")

    user_message = payload.message.strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Message is required")

    retrieval_error: str | None = None
    try:
        hits = hybrid_search(
            session=session,
            matter_id=str(matter.id),
            user_id=auth.user.id,
            query=user_message,
            limit=payload.limit,
            vector_limit=max(30, payload.limit * 4),
            lexical_limit=max(30, payload.limit * 4),
        )
    except Exception as exc:  # noqa: BLE001
        # Keep agent chat available even when embedding/vector search config is absent.
        hits = []
        retrieval_error = str(exc)

    citations = [
        {
            "document_id": hit.document_id,
            "original_filename": hit.original_filename,
            "page_num": hit.page_num,
            "score": hit.score,
            "text_snippet": hit.text[:350],
        }
        for hit in hits
    ]

    context_lines = []
    for index, hit in enumerate(hits, start=1):
        citation = _format_hit_label(hit.original_filename, hit.page_num, hit.document_id)
        snippet = " ".join((hit.text or "").split())
        context_lines.append(f"[{index}] {citation}\n{snippet[:1200]}")
    context_block = (
        "\n\n".join(context_lines)
        if context_lines
        else "No evidence excerpts matched this query."
    )

    prompt = (
        "You are OpenClaw, a federal criminal defense assistant for Acquittify.\n"
        "Answer the user using the provided evidence excerpts.\n"
        "When making factual claims, cite the excerpt ids in square brackets like [1] [2].\n"
        "If evidence is missing or uncertain, say so directly and suggest the best next query.\n\n"
        f"User question:\n{user_message}\n\n"
        f"Evidence excerpts:\n{context_block}\n\n"
        "Return a concise, practical response in plain text."
    )

    settings = get_settings()
    agent_model = _resolve_agent_model(settings)
    llm_configured = _is_llm_configured_for_agent(settings, agent_model)
    if not llm_configured:
        summary = _build_extractive_fallback_answer(
            user_message=user_message,
            context_lines=[
                f"{index + 1}. {_format_hit_label(hit.original_filename, hit.page_num, hit.document_id)}: "
                + " ".join((hit.text or "").split())[:280]
                for index, hit in enumerate(hits)
            ],
            retrieval_error=retrieval_error,
            config_hint=_agent_config_hint(agent_model),
        )
        record_agent_usage(
            session=session,
            user_id=auth.user.id,
            organization_id=auth.organization.id,
            matter_id=matter.id,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            model=None,
            used_search_fallback=True,
        )
        session.commit()
        return {
            "answer": summary,
            "model": None,
            "citations": citations,
            "used_search_fallback": True,
            "retrieval_error": retrieval_error,
        }

    try:
        completion = LLMClient().complete_text_with_usage(
            prompt=prompt,
            model=agent_model,
            temperature=0.1,
        )
    except Exception as exc:  # noqa: BLE001
        fallback = (
            "OpenClaw could not reach the configured LLM provider right now. "
            "Search evidence is available below."
        )
        record_agent_usage(
            session=session,
            user_id=auth.user.id,
            organization_id=auth.organization.id,
            matter_id=matter.id,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            model=agent_model,
            used_search_fallback=True,
        )
        session.commit()
        return {
            "answer": fallback,
            "model": agent_model,
            "citations": citations,
            "used_search_fallback": True,
            "llm_error": str(exc),
        }

    record_agent_usage(
        session=session,
        user_id=auth.user.id,
        organization_id=auth.organization.id,
        matter_id=matter.id,
        prompt_tokens=completion.prompt_tokens,
        completion_tokens=completion.completion_tokens,
        total_tokens=completion.total_tokens,
        model=agent_model,
        used_search_fallback=False,
    )
    session.commit()

    return {
        "answer": (completion.text or "").strip() or "No answer was generated.",
        "model": agent_model,
        "citations": citations,
        "used_search_fallback": False,
        "usage": {
            "prompt_tokens": completion.prompt_tokens,
            "completion_tokens": completion.completion_tokens,
            "total_tokens": completion.total_tokens,
        },
    }
