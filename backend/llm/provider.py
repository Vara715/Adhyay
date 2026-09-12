"""Replaceable provider interface; this module intentionally contains no SDK integration."""

from abc import ABC, abstractmethod

from backend.models.llm import LLMRequest, LLMResponse


class LLMProvider(ABC):
    """Adapter contract implemented by a provider-specific integration later."""

    @abstractmethod
    def complete(self, request: LLMRequest, *, model: str) -> LLMResponse:
        """Return normalized text or one normalized tool call for a request."""
