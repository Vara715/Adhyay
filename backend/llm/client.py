"""Provider-neutral LLM client with configuration checks that never expose secrets."""

from backend.config import Settings
from backend.llm.provider import LLMProvider
from backend.models.llm import LLMRequest, LLMResponse


class LLMConfigurationError(RuntimeError):
    """Raised only when a caller attempts LLM work without complete configuration."""


class LLMClient:
    """Delegates to an injected provider, keeping the future agent provider-agnostic."""

    def __init__(self, provider: LLMProvider, model: str) -> None:
        self._provider = provider
        self._model = model

    @classmethod
    def from_settings(cls, settings: Settings, provider: LLMProvider) -> "LLMClient":
        if not settings.llm_is_configured:
            raise LLMConfigurationError(settings.llm_configuration_message or "LLM is not configured.")
        # API-key ownership remains inside a future provider adapter; it is never logged or returned.
        return cls(provider=provider, model=settings.llm_model or "")

    def complete(self, request: LLMRequest) -> LLMResponse:
        return self._provider.complete(request, model=self._model)
