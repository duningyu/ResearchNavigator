import json

import httpx
import pytest

from research_navigator.analysis import providers


def test_openai_provider_sends_only_evidence_with_json_schema_and_auth() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "Supported claim",
                                    "methods": [],
                                    "datasets": [],
                                    "metrics": [],
                                    "citations": [{"field": "summary", "chunk_id": 9}],
                                }
                            )
                        }
                    }
                ]
            },
        )

    provider = providers.OpenAICompatibleProvider(
        base_url="https://llm.example/v1/",
        api_key="top-secret",
        model="audit-model",
        prompt_version="paper-analysis-v1",
        transport=httpx.MockTransport(handler),
    )

    result = provider.complete(snippets=[{"chunk_id": 9, "text": "Supported claim"}])

    assert result["summary"] == "Supported claim"
    assert captured["url"] == "https://llm.example/v1/chat/completions"
    assert captured["authorization"] == "Bearer top-secret"
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["model"] == "audit-model"
    assert body["response_format"]["type"] == "json_schema"
    prompt = body["messages"][1]["content"]
    assert "Supported claim" in prompt
    assert "top-secret" not in prompt


def test_ollama_provider_uses_native_structured_chat_without_auth_header() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": json.dumps(
                        {
                            "summary": "Local evidence",
                            "methods": [],
                            "datasets": [],
                            "metrics": [],
                            "citations": [{"field": "summary", "chunk_id": 3}],
                        }
                    )
                }
            },
        )

    provider = providers.OllamaProvider(
        base_url="http://127.0.0.1:11434",
        model="qwen-local",
        prompt_version="paper-analysis-v1",
        transport=httpx.MockTransport(handler),
    )

    result = provider.complete(snippets=[{"chunk_id": 3, "text": "Local evidence"}])

    assert result["summary"] == "Local evidence"
    assert captured["url"] == "http://127.0.0.1:11434/api/chat"
    assert captured["authorization"] is None
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["model"] == "qwen-local"
    assert body["stream"] is False
    assert body["format"]["type"] == "object"


def test_provider_retries_429_once_then_returns_valid_payload() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, json={"error": "rate limited"})
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "Recovered",
                                    "methods": [],
                                    "datasets": [],
                                    "metrics": [],
                                    "citations": [{"field": "summary", "chunk_id": 1}],
                                }
                            )
                        }
                    }
                ]
            },
        )

    provider = providers.OpenAICompatibleProvider(
        base_url="https://llm.example/v1",
        api_key="secret-key",
        model="audit-model",
        prompt_version="paper-analysis-v1",
        max_attempts=2,
        transport=httpx.MockTransport(handler),
    )

    assert provider.complete(snippets=[{"chunk_id": 1, "text": "Recovered"}])["summary"] == (
        "Recovered"
    )
    assert attempts == 2


def test_provider_failure_does_not_expose_api_key() -> None:
    provider = providers.OpenAICompatibleProvider(
        base_url="https://llm.example/v1",
        api_key="never-log-this-key",
        model="audit-model",
        prompt_version="paper-analysis-v1",
        max_attempts=1,
        transport=httpx.MockTransport(lambda request: httpx.Response(503, text="unavailable")),
    )

    with pytest.raises(providers.ProviderRequestError) as exc_info:
        provider.complete(snippets=[{"chunk_id": 1, "text": "Evidence"}])

    assert "never-log-this-key" not in str(exc_info.value)
