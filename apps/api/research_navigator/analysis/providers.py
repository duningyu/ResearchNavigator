"""Evidence-bounded structured extraction provider interfaces."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from research_navigator.analysis.structured import EvidenceLevel
from research_navigator.config import Settings

ABSTENTION = "未在当前可访问文本中找到。"
_FIELDS = (
    "executive_summary",
    "research_background",
    "research_problem",
    "theoretical_contribution",
    "method_innovation",
    "research_route",
    "inputs",
    "outputs",
    "core_methods",
    "new_modules",
    "datasets",
    "baselines",
    "metrics",
    "experimental_protocol",
    "major_results",
    "claimed_contributions",
    "future_work_explicit",
    "limitations_author_stated",
    # Backward-compatible provider fields.
    "summary",
    "methods",
)


class CitationValidationError(ValueError):
    """Raised when a model claims a field without citing supplied evidence."""


class ProviderRequestError(RuntimeError):
    """A bounded provider request failed without exposing credentials or response bodies."""


class ProviderCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    chunk_id: int | str | None


class ProviderExtraction(BaseModel):
    """Strict structured-output contract shared by remote and local providers."""

    model_config = ConfigDict(extra="forbid")

    executive_summary: str | None = None
    research_background: str | None = None
    research_problem: str | None = None
    theoretical_contribution: list[str] = Field(default_factory=list)
    method_innovation: list[str] = Field(default_factory=list)
    research_route: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    core_methods: list[str] = Field(default_factory=list)
    new_modules: list[str] = Field(default_factory=list)
    datasets: list[str] = Field(default_factory=list)
    baselines: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    experimental_protocol: list[str] = Field(default_factory=list)
    major_results: list[str] = Field(default_factory=list)
    claimed_contributions: list[str] = Field(default_factory=list)
    future_work_explicit: list[str] = Field(default_factory=list)
    limitations_author_stated: list[str] = Field(default_factory=list)
    summary: str | None = None
    methods: list[str] = Field(default_factory=list)
    citations: list[ProviderCitation] = Field(default_factory=list)


def _evidence_prompt(
    *, snippets: Sequence[Mapping[str, Any]], prompt_version: str
) -> str:
    evidence = [
        {"chunk_id": snippet.get("chunk_id"), "text": str(snippet.get("text", ""))}
        for snippet in snippets
    ]
    return json.dumps(
        {
            "prompt_version": prompt_version,
            "instruction": (
                "Extract only claims supported by the supplied evidence. Cite every non-empty "
                "field with its chunk_id and abstain by leaving unsupported fields empty."
            ),
            "evidence": evidence,
        },
        ensure_ascii=False,
    )


class _StructuredHTTPProvider:
    provider_name = "http"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        prompt_version: str,
        timeout_seconds: float = 20.0,
        max_attempts: int = 2,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not base_url.strip():
            raise ValueError("base_url is required")
        if not model.strip():
            raise ValueError("model is required")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        self.base_url = base_url.rstrip("/")
        self.model_name = model
        self.prompt_version = prompt_version
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.transport = transport

    def _request(self, *, path: str, payload: Mapping[str, Any], headers: Mapping[str, str]) -> Any:
        for attempt in range(1, self.max_attempts + 1):
            try:
                with httpx.Client(
                    timeout=self.timeout_seconds,
                    transport=self.transport,
                    follow_redirects=False,
                ) as client:
                    response = client.post(f"{self.base_url}{path}", json=payload, headers=headers)
                if (
                    response.status_code == 429 or response.status_code >= 500
                ) and attempt < self.max_attempts:
                    continue
                response.raise_for_status()
                return response.json()
            except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as exc:
                retryable = isinstance(exc, httpx.RequestError)
                if isinstance(exc, httpx.HTTPStatusError):
                    retryable = exc.response.status_code == 429 or exc.response.status_code >= 500
                if retryable and attempt < self.max_attempts:
                    continue
                raise ProviderRequestError(
                    f"{self.provider_name} request failed after {attempt} attempt(s)"
                ) from None
        raise ProviderRequestError(
            f"{self.provider_name} request failed after {self.max_attempts} attempt(s)"
        )

    @staticmethod
    def _validate_content(content: Any) -> dict[str, Any]:
        try:
            raw = json.loads(content) if isinstance(content, str) else content
            return ProviderExtraction.model_validate(raw).model_dump()
        except (json.JSONDecodeError, ValidationError, TypeError):
            raise ProviderRequestError("provider returned invalid structured output") from None


class OpenAICompatibleProvider(_StructuredHTTPProvider):
    """OpenAI-compatible chat-completions client with bounded structured output."""

    provider_name = "openai_compatible"

    def __init__(self, *, api_key: str, **kwargs: Any) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        super().__init__(**kwargs)
        self._api_key = api_key

    def complete(self, *, snippets: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        schema = ProviderExtraction.model_json_schema()
        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": "Return evidence-bounded JSON matching the supplied schema.",
                },
                {
                    "role": "user",
                    "content": _evidence_prompt(
                        snippets=snippets, prompt_version=self.prompt_version
                    ),
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "paper_evidence_extraction",
                    "strict": True,
                    "schema": schema,
                },
            },
        }
        response = self._request(
            path="/chat/completions",
            payload=payload,
            headers={"Authorization": f"Bearer {self._api_key}"},
        )
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise ProviderRequestError("provider returned invalid structured output") from None
        return self._validate_content(content)


class OllamaProvider(_StructuredHTTPProvider):
    """Native Ollama chat client using Ollama's JSON-schema format contract."""

    provider_name = "ollama"

    def complete(self, *, snippets: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        schema = ProviderExtraction.model_json_schema()
        payload = {
            "model": self.model_name,
            "stream": False,
            "messages": [
                {
                    "role": "system",
                    "content": "Return evidence-bounded JSON matching the supplied schema.",
                },
                {
                    "role": "user",
                    "content": _evidence_prompt(
                        snippets=snippets, prompt_version=self.prompt_version
                    ),
                },
            ],
            "format": schema,
        }
        response = self._request(path="/api/chat", payload=payload, headers={})
        try:
            content = response["message"]["content"]
        except (KeyError, TypeError):
            raise ProviderRequestError("provider returned invalid structured output") from None
        return self._validate_content(content)


class DeterministicMockProvider:
    """Test provider; it never performs network access."""

    provider_name = "deterministic_mock"
    model_name = "mock-v1"

    def __init__(self, response: Mapping[str, Any]) -> None:
        self.response = dict(response)

    def complete(self, *, snippets: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        return dict(self.response)


class EvidenceBoundLLMProvider:
    """Validate provider JSON against the chunks supplied to the provider."""

    def __init__(self, complete: Any) -> None:
        self.complete = complete

    def extract(
        self,
        *,
        paper_id: int,
        evidence_level: EvidenceLevel,
        snippets: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        payload = self.complete.complete(snippets=snippets)
        citations = payload.get("citations", [])
        if not isinstance(citations, list):
            raise CitationValidationError("citations must be a list")
        allowed_chunks = {item.get("chunk_id") for item in snippets}
        cited_fields: dict[str, set[Any]] = {}
        for citation in citations:
            if not isinstance(citation, Mapping) or not isinstance(citation.get("field"), str):
                raise CitationValidationError("each citation needs a field")
            chunk_id = citation.get("chunk_id")
            if chunk_id not in allowed_chunks:
                raise CitationValidationError(f"citation chunk {chunk_id!r} was not supplied")
            cited_fields.setdefault(citation["field"], set()).add(chunk_id)

        result: dict[str, Any] = {
            "paper_id": paper_id,
            "evidence_level": evidence_level,
            "citations": citations,
            "missing_fields": [],
            "abstentions": [],
        }
        for field in _FIELDS:
            value = payload.get(field)
            if value and field not in cited_fields:
                raise CitationValidationError(f"field {field!r} has no supported citation")
            if value:
                result[field] = value
            else:
                result[field] = [] if field in {"methods", "datasets", "metrics"} else ABSTENTION
                result["missing_fields"].append(field)
                result["abstentions"].append(ABSTENTION)
        return result


def build_analysis_provider(settings: Settings) -> object | None:
    """Build the configured provider, returning None for deterministic mode.

    Missing provider credentials/configuration degrade to deterministic analysis;
    callers persist the fallback reason rather than failing the analysis API.
    """

    mode = settings.analysis_provider.strip().lower()
    if mode in {"", "deterministic", "none"}:
        return None
    if mode == "openai_compatible":
        if not settings.llm_base_url or not settings.llm_api_key or not settings.llm_model:
            return None
        return OpenAICompatibleProvider(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            prompt_version=settings.analysis_prompt_version,
            timeout_seconds=settings.llm_timeout_seconds,
            max_attempts=settings.llm_max_attempts,
        )
    if mode == "ollama":
        if not settings.llm_base_url or not settings.llm_model:
            return None
        return OllamaProvider(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            prompt_version=settings.analysis_prompt_version,
            timeout_seconds=settings.llm_timeout_seconds,
            max_attempts=settings.llm_max_attempts,
        )
    raise ValueError(f"Unsupported analysis provider: {mode}")
