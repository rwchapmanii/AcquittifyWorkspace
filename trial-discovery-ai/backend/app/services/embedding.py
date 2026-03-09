from dataclasses import dataclass

from openai import OpenAI

from app.core.config import get_settings


@dataclass(frozen=True)
class EmbeddingResult:
    vector: list[float]


def embed_text(text: str) -> EmbeddingResult:
    settings = get_settings()
    api_key = (
        settings.embedding_api_key
        or settings.llm_api_key
        or settings.openai_api_key
    )
    base_url = (settings.embedding_base_url or settings.llm_base_url or "").strip()
    if base_url.startswith("ws://"):
        base_url = "http://" + base_url[len("ws://") :]
    elif base_url.startswith("wss://"):
        base_url = "https://" + base_url[len("wss://") :]
    base_url = base_url.rstrip("/")
    if not base_url:
        base_url = None
    if not api_key and not base_url:
        raise RuntimeError(
            "EMBEDDING_API_KEY/LLM_API_KEY/OPENAI_API_KEY or EMBEDDING_BASE_URL is not set"
        )
    if not api_key and base_url:
        api_key = "local"
    default_headers: dict[str, str] = {}
    if base_url and settings.openclaw_agent_id:
        default_headers["x-openclaw-agent-id"] = settings.openclaw_agent_id
    if base_url:
        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers=default_headers,
        )
    else:
        client = OpenAI(api_key=api_key)
    embedding_kwargs = {
        "model": settings.embedding_model,
        "input": text,
    }
    # OpenAI text-embedding-3 models support dimension down-projection.
    if (
        settings.embedding_model.startswith("text-embedding-3")
        and settings.embedding_dim > 0
    ):
        embedding_kwargs["dimensions"] = settings.embedding_dim
    response = client.embeddings.create(**embedding_kwargs)
    return EmbeddingResult(vector=response.data[0].embedding)
