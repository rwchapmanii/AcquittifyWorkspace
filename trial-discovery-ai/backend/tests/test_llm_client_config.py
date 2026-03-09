from types import SimpleNamespace

from app.core.llm.client import LLMClient, _normalize_openai_base_url
from app.services import embedding as embedding_service


def test_normalize_openai_base_url_strips_responses_endpoint() -> None:
    assert (
        _normalize_openai_base_url("http://127.0.0.1:18789/v1/responses")
        == "http://127.0.0.1:18789/v1"
    )


def test_llm_client_uses_normalized_base_url_and_agent_header(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeOpenAI:
        def __init__(
            self, *, api_key: str, base_url: str | None = None, default_headers=None
        ) -> None:
            captured["api_key"] = api_key
            captured["base_url"] = base_url
            captured["default_headers"] = default_headers or {}
            self.responses = SimpleNamespace(create=lambda **_: SimpleNamespace(output_text="ok"))

    class _FakeSettings:
        llm_api_key = "llm-token"
        openai_api_key = None
        llm_base_url = "http://127.0.0.1:18789/v1/responses"
        openclaw_agent_id = "acquittify"

    monkeypatch.setattr("app.core.llm.client.OpenAI", _FakeOpenAI)
    monkeypatch.setattr("app.core.llm.client.get_settings", lambda: _FakeSettings())

    LLMClient()

    assert captured["api_key"] == "llm-token"
    assert captured["base_url"] == "http://127.0.0.1:18789/v1"
    assert captured["default_headers"] == {"x-openclaw-agent-id": "acquittify"}


def test_embed_text_does_not_inherit_llm_base_url(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeOpenAI:
        def __init__(
            self, *, api_key: str, base_url: str | None = None, default_headers=None
        ) -> None:
            captured["api_key"] = api_key
            captured["base_url"] = base_url
            captured["default_headers"] = default_headers or {}
            self.embeddings = SimpleNamespace(
                create=lambda **_: SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2])])
            )

    class _FakeSettings:
        embedding_api_key = None
        llm_api_key = None
        openai_api_key = "openai-key"
        embedding_base_url = ""
        llm_base_url = "http://127.0.0.1:18789/v1/responses"
        openclaw_agent_id = "acquittify"
        embedding_model = "text-embedding-3-large"
        embedding_dim = 768

    monkeypatch.setattr(embedding_service, "OpenAI", _FakeOpenAI)
    monkeypatch.setattr(embedding_service, "get_settings", lambda: _FakeSettings())

    result = embedding_service.embed_text("hello world")

    assert result.vector == [0.1, 0.2]
    assert captured["api_key"] == "openai-key"
    assert captured["base_url"] is None
    assert captured["default_headers"] == {}
