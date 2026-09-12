"""Tests for the provider-neutral LLM boundary and safe configuration behavior."""

import unittest

from backend.config import Settings
from backend.llm.client import LLMClient, LLMConfigurationError
from backend.llm.provider import LLMProvider
from backend.models.llm import LLMMessage, LLMRequest, LLMResponse


class FakeProvider(LLMProvider):
    def __init__(self) -> None:
        self.model: str | None = None

    def complete(self, request: LLMRequest, *, model: str) -> LLMResponse:
        self.model = model
        return LLMResponse(content="Provider response")


class LLMClientTests(unittest.TestCase):
    def test_missing_configuration_fails_with_safe_message(self) -> None:
        with self.assertRaisesRegex(LLMConfigurationError, "LLM is not configured"):
            LLMClient.from_settings(Settings(), FakeProvider())

    def test_client_delegates_through_injected_provider(self) -> None:
        settings = Settings(llm_provider="example", llm_api_key="secret", llm_model="demo-model")
        provider = FakeProvider()
        client = LLMClient.from_settings(settings, provider)
        response = client.complete(LLMRequest(messages=[LLMMessage(role="user", content="Investigate")]))
        self.assertEqual(response.content, "Provider response")
        self.assertEqual(provider.model, "demo-model")

    def test_configuration_message_never_includes_api_key(self) -> None:
        settings = Settings(llm_provider="example", llm_api_key="top-secret", llm_model=None)
        self.assertNotIn("top-secret", settings.llm_configuration_message or "")


if __name__ == "__main__":
    unittest.main()
