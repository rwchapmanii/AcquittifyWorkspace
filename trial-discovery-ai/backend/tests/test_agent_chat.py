from types import SimpleNamespace
import uuid

from fastapi.testclient import TestClient

import app.api.routes.agent as agent_route


def _csrf_headers(client: TestClient) -> dict[str, str]:
    token = client.cookies.get("peregrine_csrf")
    assert token
    return {"X-CSRF-Token": token}


def _register(client: TestClient) -> dict:
    response = client.post(
        "/auth/register",
        json={
            "email": f"agent-{uuid.uuid4().hex}@example.test",
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _create_matter(client: TestClient, *, name: str) -> str:
    response = client.post(
        "/matters",
        json={"name": name},
        headers=_csrf_headers(client),
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def test_agent_chat_returns_search_fallback_when_llm_not_configured(
    client: TestClient, monkeypatch
) -> None:
    _register(client)
    matter_id = _create_matter(client, name="Agent Fallback Matter")

    monkeypatch.setattr(
        agent_route,
        "hybrid_search",
        lambda **_: [
            SimpleNamespace(
                chunk_id="chunk-1",
                document_id="doc-1",
                score=0.99,
                page_num=2,
                text="Cross examination excerpt for fallback test.",
                source_path="s3://bucket/doc-1.txt",
                original_filename="cross_exam.txt",
            )
        ],
    )

    response = client.post(
        f"/matters/{matter_id}/agent/chat",
        json={"message": "Summarize cross exam"},
        headers=_csrf_headers(client),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["used_search_fallback"] is True
    answer = str(body["answer"]).lower()
    assert "search fallback answer" in answer
    assert "no llm configured" in answer
    assert "cross_exam.txt" in answer
    assert len(body["citations"]) == 1


def test_agent_chat_uses_llm_when_configured(client: TestClient, monkeypatch) -> None:
    _register(client)
    matter_id = _create_matter(client, name="Agent LLM Matter")

    monkeypatch.setattr(
        agent_route,
        "hybrid_search",
        lambda **_: [
            SimpleNamespace(
                chunk_id="chunk-2",
                document_id="doc-2",
                score=0.88,
                page_num=5,
                text="Witness statement excerpt for llm test.",
                source_path="s3://bucket/doc-2.txt",
                original_filename="witness_statement.txt",
            )
        ],
    )

    class _FakeSettings:
        llm_base_url = "http://llm.internal/v1"
        llm_api_key = "test"
        openai_api_key = None
        llm_model = "test-llm"
        agent_model = "test-openclaw"

    class _FakeLLMClient:
        class _Result:
            text = "OpenClaw summary with citation [1]."
            prompt_tokens = 11
            completion_tokens = 7
            total_tokens = 18

        def complete_text_with_usage(
            self, *, prompt: str, model: str, temperature: float
        ) -> "_FakeLLMClient._Result":
            assert "Witness statement excerpt" in prompt
            assert model == "test-openclaw"
            return _FakeLLMClient._Result()

    monkeypatch.setattr(agent_route, "get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(agent_route, "LLMClient", _FakeLLMClient)

    response = client.post(
        f"/matters/{matter_id}/agent/chat",
        json={"message": "What does the witness say?"},
        headers=_csrf_headers(client),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["used_search_fallback"] is False
    assert body["model"] == "test-openclaw"
    assert "OpenClaw summary" in body["answer"]


def test_agent_chat_openclaw_requires_base_url(client: TestClient, monkeypatch) -> None:
    _register(client)
    matter_id = _create_matter(client, name="Agent OpenClaw Base URL Matter")

    monkeypatch.setattr(
        agent_route,
        "hybrid_search",
        lambda **_: [
            SimpleNamespace(
                chunk_id="chunk-3",
                document_id="doc-3",
                score=0.91,
                page_num=1,
                text="Excerpt for base URL check.",
                source_path="s3://bucket/doc-3.txt",
                original_filename="base_url_check.txt",
            )
        ],
    )

    class _FakeSettings:
        llm_base_url = ""
        llm_api_key = ""
        openai_api_key = "openai-only-key"
        llm_model = "legacy-model"
        agent_model = "openclaw"

    class _NeverLLMClient:
        def __init__(self) -> None:
            raise AssertionError("LLMClient should not be called without OpenClaw base URL")

    monkeypatch.setattr(agent_route, "get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(agent_route, "LLMClient", _NeverLLMClient)

    response = client.post(
        f"/matters/{matter_id}/agent/chat",
        json={"message": "Do we have anything useful?"},
        headers=_csrf_headers(client),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["used_search_fallback"] is True
    assert body["model"] is None
    assert "no llm configured" in str(body["answer"]).lower()


def test_agent_chat_handles_retrieval_errors_without_500(
    client: TestClient, monkeypatch
) -> None:
    _register(client)
    matter_id = _create_matter(client, name="Agent Retrieval Error Matter")

    def _raise(**_kwargs):
        raise RuntimeError("EMBEDDING_API_KEY missing")

    monkeypatch.setattr(agent_route, "hybrid_search", _raise)

    response = client.post(
        f"/matters/{matter_id}/agent/chat",
        json={"message": "Summarize the case"},
        headers=_csrf_headers(client),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["used_search_fallback"] is True
    assert body["retrieval_error"] is not None
    assert "embedding" in body["retrieval_error"].lower()


def test_agent_chat_accepts_large_bootstrap_sized_message(
    client: TestClient, monkeypatch
) -> None:
    _register(client)
    matter_id = _create_matter(client, name="Agent Large Prompt Matter")

    monkeypatch.setattr(agent_route, "hybrid_search", lambda **_: [])

    response = client.post(
        f"/matters/{matter_id}/agent/chat",
        json={"message": "A" * 12000},
        headers=_csrf_headers(client),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["used_search_fallback"] is True


def test_agent_chat_accepts_query_alias_payload(client: TestClient, monkeypatch) -> None:
    _register(client)
    matter_id = _create_matter(client, name="Agent Query Alias Matter")

    monkeypatch.setattr(agent_route, "hybrid_search", lambda **_: [])

    response = client.post(
        f"/matters/{matter_id}/agent/chat",
        json={"query": "Run bootstrap schema analysis"},
        headers=_csrf_headers(client),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["used_search_fallback"] is True
