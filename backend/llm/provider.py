"""Provider interface plus a real, working adapter for open-weight models.

``LLMProvider`` is the contract every adapter must satisfy. ``OpenAICompatibleProvider``
is a concrete adapter that speaks the OpenAI ``/chat/completions`` wire format, which is
what almost every open-weight serving stack exposes: Ollama, vLLM, LM Studio, llama.cpp's
``server``, Groq, Together AI, Fireworks, and others. Pointing ``LLM_BASE_URL`` at any of
those turns the agent's "brain" into whichever open-weight model that server is running
(Llama, Qwen, Mixtral, DeepSeek, etc.) — no code change needed, only configuration.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

import httpx

from backend.models.llm import LLMRequest, LLMResponse
from backend.models.tools import ToolCall


class LLMProvider(ABC):
    """Adapter contract implemented by a provider-specific integration."""

    @abstractmethod
    def complete(self, request: LLMRequest, *, model: str) -> LLMResponse:
        """Return normalized text or one normalized tool call for a request."""


class LLMProviderError(RuntimeError):
    """Raised when a provider adapter cannot obtain or parse a completion."""


# Known open-weight-friendly OpenAI-compatible endpoints. LLM_BASE_URL always wins if set;
# these are just sensible defaults so someone only has to set LLM_PROVIDER for the common cases.
_KNOWN_BASE_URLS = {
    "ollama": "http://localhost:11434/v1",
    "vllm": "http://localhost:8000/v1",
    "lmstudio": "http://localhost:1234/v1",
    "llamacpp": "http://localhost:8080/v1",
    "groq": "https://api.groq.com/openai/v1",
    "together": "https://api.together.xyz/v1",
    "fireworks": "https://api.fireworks.ai/inference/v1",
}


class OpenAICompatibleProvider(LLMProvider):
    """Calls any OpenAI-compatible ``/chat/completions`` endpoint with tool-calling enabled.

    This is the one concrete class the project's own docstring said was missing: something
    on the other end of ``LLM_API_KEY`` that actually calls a model. It works unmodified
    against locally-hosted open-weight models (Ollama, vLLM, LM Studio, llama.cpp) as well
    as hosted open-weight inference providers (Groq, Together, Fireworks) since they all
    implement the same request/response shape.
    """

    def __init__(self, base_url: str, api_key: str, *, timeout_seconds: float = 45.0, temperature: float = 0.2) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._temperature = temperature

    @staticmethod
    def _tool_schema(tools) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                },
            }
            for tool in tools
        ]

    def complete(self, request: LLMRequest, *, model: str) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": message.role, "content": message.content} for message in request.messages],
            "temperature": self._temperature,
        }
        if request.tools:
            payload["tools"] = self._tool_schema(request.tools)
            payload["tool_choice"] = "auto"

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            response = httpx.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPStatusError as error:
            raise LLMProviderError(
                f"LLM endpoint returned {error.response.status_code}: {error.response.text[:300]}"
            ) from error
        except httpx.HTTPError as error:
            raise LLMProviderError(f"Could not reach the LLM endpoint at {self._base_url}: {error}") from error
        except (ValueError, KeyError, IndexError) as error:
            raise LLMProviderError(f"LLM endpoint returned an unparseable response: {error}") from error

        return self._normalize(body)

    @staticmethod
    def _normalize(body: dict[str, Any]) -> LLMResponse:
        try:
            message = body["choices"][0]["message"]
        except (KeyError, IndexError) as error:
            raise LLMProviderError(f"LLM response had no choices/message: {body}") from error

        content = message.get("content") or None
        raw_tool_calls = message.get("tool_calls") or []
        tool_call: ToolCall | None = None
        if raw_tool_calls:
            first = raw_tool_calls[0]
            function = first.get("function", {})
            name = function.get("name", "")
            raw_arguments = function.get("arguments", "{}")
            try:
                arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else dict(raw_arguments)
            except (json.JSONDecodeError, TypeError):
                arguments = {}
            tool_call = ToolCall(name=name, arguments=arguments)

        if content is None and tool_call is None:
            content = "The model returned an empty response."

        return LLMResponse(content=content, tool_call=tool_call)


def build_llm_provider(settings) -> LLMProvider:
    """Construct the concrete provider described by ``settings``.

    Raises ``LLMProviderError`` on unusable configuration (e.g. a custom/unknown provider
    name with no explicit ``LLM_BASE_URL``) so the caller can fall back to the rule-based
    provider instead of silently doing nothing.
    """
    provider_name = (settings.llm_provider or "").strip().lower()
    base_url = settings.llm_base_url or _KNOWN_BASE_URLS.get(provider_name)
    if not base_url:
        raise LLMProviderError(
            f"No base URL known for LLM_PROVIDER='{settings.llm_provider}'. "
            "Set LLM_BASE_URL explicitly to any OpenAI-compatible /v1 endpoint."
        )
    api_key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else ""
    return OpenAICompatibleProvider(base_url=base_url, api_key=api_key)


def test_llm_provider_connection(settings) -> tuple[bool, str]:
    """Test reachability and validity of configured LLM provider without exposing secrets."""
    if not settings.llm_is_configured:
        return False, "LLM settings incomplete. Provider, model, and API key are required."

    try:
        provider = build_llm_provider(settings)
    except LLMProviderError as err:
        return False, str(err)

    if not isinstance(provider, OpenAICompatibleProvider):
        return True, "Provider configured."

    base_url = provider._base_url
    headers = {"Content-Type": "application/json"}
    if provider._api_key:
        headers["Authorization"] = f"Bearer {provider._api_key}"

    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{base_url}/models", headers=headers)
            if resp.status_code in (200, 201):
                return True, f"Successfully connected to {base_url}"
            if resp.status_code in (401, 403):
                return False, f"Authentication failed (HTTP {resp.status_code}). Check API key."

            payload = {
                "model": settings.llm_model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
            }
            resp_chat = client.post(f"{base_url}/chat/completions", json=payload, headers=headers)
            if resp_chat.status_code in (200, 201):
                return True, f"Successfully verified connection to model '{settings.llm_model}'"
            elif resp_chat.status_code in (401, 403):
                return False, f"Authentication failed (HTTP {resp_chat.status_code}). Check API key."
            elif resp_chat.status_code == 404:
                return False, f"Endpoint or model not found (HTTP 404) at {base_url}."
            else:
                return False, f"LLM server returned status code {resp_chat.status_code}."
    except httpx.ConnectError:
        return False, f"Could not connect to LLM server at {base_url}. Ensure the server is running."
    except httpx.TimeoutException:
        return False, f"Connection to LLM server timed out at {base_url}."
    except Exception as exc:
        return False, f"LLM connection error: {type(exc).__name__}"

