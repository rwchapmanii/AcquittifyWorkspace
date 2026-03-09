import json
from dataclasses import dataclass
from hashlib import sha256

from openai import OpenAI

from app.core.config import get_settings


class LLMClient:
    def __init__(self) -> None:
        settings = get_settings()
        api_key = settings.llm_api_key or settings.openai_api_key
        base_url = (settings.llm_base_url or "").strip()
        if base_url.startswith("ws://"):
            base_url = "http://" + base_url[len("ws://") :]
        elif base_url.startswith("wss://"):
            base_url = "https://" + base_url[len("wss://") :]
        base_url = base_url.rstrip("/")
        if not base_url:
            base_url = None
        default_headers: dict[str, str] = {}
        if base_url and settings.openclaw_agent_id:
            default_headers["x-openclaw-agent-id"] = settings.openclaw_agent_id
        if not api_key and not base_url:
            raise RuntimeError("LLM_API_KEY/OPENAI_API_KEY or LLM_BASE_URL is not set")
        if not api_key and base_url:
            api_key = "local"
        if base_url:
            self._client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                default_headers=default_headers,
            )
        else:
            self._client = OpenAI(api_key=api_key)

    def complete_text(self, *, prompt: str, model: str, temperature: float) -> str:
        result = self.complete_text_with_usage(
            prompt=prompt,
            model=model,
            temperature=temperature,
        )
        return result.text

    def complete_text_with_usage(
        self, *, prompt: str, model: str, temperature: float
    ) -> "CompletionResult":
        response = self._client.responses.create(
            model=model,
            temperature=temperature,
            input=prompt,
        )
        usage = getattr(response, "usage", None)
        prompt_tokens = _coerce_token_count(usage, "input_tokens")
        completion_tokens = _coerce_token_count(usage, "output_tokens")
        total_tokens = _coerce_token_count(usage, "total_tokens")
        if total_tokens is None:
            total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)
        return CompletionResult(
            text=response.output_text or "",
            prompt_tokens=prompt_tokens or 0,
            completion_tokens=completion_tokens or 0,
            total_tokens=total_tokens or 0,
        )

    def complete_json(self, *, prompt: str, model: str, temperature: float) -> dict:
        text = self.complete_text(prompt=prompt, model=model, temperature=temperature)
        return json.loads(text)

    @staticmethod
    def prompt_hash(prompt: str) -> str:
        return sha256(prompt.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CompletionResult:
    text: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


def _coerce_token_count(usage: object, field: str) -> int | None:
    if usage is None:
        return None
    value = None
    if hasattr(usage, field):
        value = getattr(usage, field)
    elif isinstance(usage, dict):
        value = usage.get(field)
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
