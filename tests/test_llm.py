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


class MockLLMProvider(LLMProvider):
    def __init__(self, responses: list[LLMResponse] | None = None) -> None:
        self.responses = list(responses or [])
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest, *, model: str) -> LLMResponse:
        self.requests.append(request)
        if self.responses:
            return self.responses.pop(0)
        return LLMResponse(content="Mock default response")


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


class LLMDecisionProviderTests(unittest.TestCase):
    def test_llm_decision_provider_returns_tool_decision(self) -> None:
        from backend.agent.decisions import LLMDecisionProvider
        from backend.models.agent import AgentState
        from backend.models.tools import ToolCall, ToolMetadata

        mock_provider = MockLLMProvider([
            LLMResponse(content="I should lookup customer order details.", tool_call=ToolCall(name="get_order", arguments={"order_id": "ORD-9002"})),
        ])
        client = LLMClient(mock_provider, "mock-model")
        provider = LLMDecisionProvider(client)

        state = AgentState(original_goal="Investigate ORD-9002")
        tools = [ToolMetadata(name="get_order", description="Get order details", input_schema={})]

        decision = provider.decide(state, tools)
        self.assertEqual(decision.kind, "tool")
        self.assertEqual(decision.tool_call.name, "get_order")
        self.assertEqual(decision.tool_call.arguments, {"order_id": "ORD-9002"})

    def test_llm_decision_provider_returns_action_decision(self) -> None:
        from backend.agent.decisions import LLMDecisionProvider
        from backend.models.agent import AgentState
        from backend.models.tools import ToolCall, ToolMetadata

        mock_provider = MockLLMProvider([
            LLMResponse(content="Item damaged in transit, replacement available.", tool_call=ToolCall(name="create_replacement", arguments={"order_id": "ORD-9002", "product_id": "PR-200"})),
        ])
        client = LLMClient(mock_provider, "mock-model")
        provider = LLMDecisionProvider(client)

        state = AgentState(original_goal="Investigate ORD-9002")
        tools = [ToolMetadata(name="create_replacement", description="Create replacement", input_schema={})]

        decision = provider.decide(state, tools)
        self.assertEqual(decision.kind, "action")
        self.assertEqual(decision.action_call.name, "create_replacement")

    def test_llm_decision_provider_rejects_unknown_tool(self) -> None:
        from backend.agent.decisions import LLMDecisionProvider
        from backend.models.agent import AgentState
        from backend.models.tools import ToolCall, ToolMetadata

        mock_provider = MockLLMProvider([
            LLMResponse(content="Hack the server", tool_call=ToolCall(name="unauthorized_tool", arguments={})),
        ])
        client = LLMClient(mock_provider, "mock-model")
        provider = LLMDecisionProvider(client)

        state = AgentState(original_goal="Investigate ORD-9002")
        tools = [ToolMetadata(name="get_order", description="Get order details", input_schema={})]

        with self.assertRaisesRegex(ValueError, "unknown or unpermitted tool"):
            provider.decide(state, tools)

    def test_controller_uses_llm_decision_and_falls_back_on_error(self) -> None:
        from decimal import Decimal
        from backend.agent.controller import AgentController
        from backend.agent.decisions import LLMDecisionProvider
        from backend.data.database import SimulatedCompanyRepository
        from backend.llm.provider import LLMProviderError
        from backend.models.tools import ToolCall, ToolMetadata
        from backend.tools.actions import ActionRegistry
        from backend.tools.registry import ToolRegistry

        class FailingProvider(LLMProvider):
            def complete(self, request: LLMRequest, *, model: str) -> LLMResponse:
                raise LLMProviderError("Simulated LLM API rate limit error.")

        repo = SimulatedCompanyRepository("customer_damaged_replacement_available")
        tool_reg = ToolRegistry(repo)
        action_reg = ActionRegistry(repo, Decimal("50000"))

        failing_client = LLMClient(FailingProvider(), "mock-model")
        controller = AgentController(tool_reg, LLMDecisionProvider(failing_client), action_registry=action_reg)

        goal = "Customer CUST-801 received defective laptop stand in order ORD-9002. Resolve the issue."
        state = controller.run(goal)

        # Should NOT fail or crash, but fall back safely to rule-based engine and resolve!
        self.assertEqual(state.status, "completed")
        self.assertIsNotNone(state.customer_case)
        self.assertEqual(state.customer_case.status, "RESOLVED")
        self.assertTrue(any(e.event_type == "adaptation" and "Falling back" in e.summary for e in state.events))


if __name__ == "__main__":
    unittest.main()
