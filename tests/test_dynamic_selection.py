"""Unit tests for Step 5 proving dynamic tool and action selection, adaptation,

failure handling, non-redundant tool calling, and LLM decision safety."""

import unittest
from decimal import Decimal
from unittest.mock import MagicMock

from backend.agent.controller import AgentController
from backend.agent.decisions import EvidenceBasedDecisionProvider, LLMDecisionProvider
from backend.data.database import SimulatedCompanyRepository
from backend.data.scenarios import FailurePlan, ScenarioDefinition, _base_data
from backend.models.llm import LLMResponse
from backend.models.tools import ToolCall
from backend.tools.actions import ActionRegistry
from backend.tools.registry import ToolRegistry


class TestDynamicSelection(unittest.TestCase):
    def setUp(self):
        self.repo = SimulatedCompanyRepository("customer_damaged_replacement_available")
        self.tool_registry = ToolRegistry(self.repo)
        self.action_registry = ActionRegistry(self.repo, Decimal("50000"))
        self.decision_provider = EvidenceBasedDecisionProvider()
        self.controller = AgentController(
            self.tool_registry,
            self.decision_provider,
            action_registry=self.action_registry,
        )

    def test_01_replacement_available_path(self):
        """TEST 1: Replacement available path selected, executed, verified -> RESOLVED."""
        goal = "My laptop stand arrived damaged in order ORD-9002. I want a replacement."
        state = self.controller.run(goal)
        self.assertEqual(state.status, "completed")
        self.assertEqual(state.customer_case.status, "RESOLVED")
        self.assertTrue(any("create_replacement" in a for a in state.actions))
        self.assertTrue(any(e.event_type == "verification" for e in state.events))

    def test_02_replacement_unavailable_adapts_path(self):
        """TEST 2: Stockout detected -> agent adapts -> refund selected, executed, verified -> RESOLVED."""
        repo = SimulatedCompanyRepository("customer_replacement_out_of_stock_adapts_refund")
        controller = AgentController(
            ToolRegistry(repo),
            EvidenceBasedDecisionProvider(),
            action_registry=ActionRegistry(repo, Decimal("50000")),
        )
        goal = "My product in order ORD-9003 arrived damaged. Please replace it."
        state = controller.run(goal)
        self.assertEqual(state.status, "completed")
        self.assertEqual(state.customer_case.status, "RESOLVED")
        # Proves adaptation: requested replacement, but executed refund after stockout
        self.assertTrue(any("issue_refund" in a for a in state.actions))
        self.assertTrue(any(e.event_type == "adaptation" for e in state.events))

    def test_03_cancellation_path(self):
        """TEST 3: Cancellation requested prior to dispatch -> cancel_order executed & verified."""
        repo = SimulatedCompanyRepository("customer_replacement_out_of_stock_adapts_refund")
        controller = AgentController(
            ToolRegistry(repo),
            EvidenceBasedDecisionProvider(),
            action_registry=ActionRegistry(repo, Decimal("50000")),
        )
        goal = "I want to cancel my order ORD-9003 because I no longer need it."
        state = controller.run(goal)
        self.assertEqual(state.status, "completed")
        self.assertEqual(state.customer_case.status, "RESOLVED")
        self.assertTrue(any("cancel_order" in a for a in state.actions))

    def test_04_policy_restriction_path(self):
        """TEST 4: Action forbidden by policy -> agent does not execute forbidden action, escalates safely."""
        repo = SimulatedCompanyRepository("customer_refund_denied_policy_escalation")
        controller = AgentController(
            ToolRegistry(repo),
            EvidenceBasedDecisionProvider(),
            action_registry=ActionRegistry(repo, Decimal("50000")),
        )
        goal = "I want to cancel my shipped order ORD-9004."
        state = controller.run(goal)
        self.assertEqual(state.status, "completed")
        self.assertEqual(state.customer_case.status, "ESCALATED")
        # Ensures forbidden action was NOT executed
        self.assertFalse(any("cancel_order" in a for a in state.actions))
        self.assertTrue(any("escalate_customer_case" in a for a in state.actions))

    def test_05_tool_failure_handling(self):
        """TEST 5: Investigation tool failure -> agent detects failure, does not fabricate data, escalates safely."""
        custom_data = _base_data()
        scenario_def = ScenarioDefinition(
            key="custom_failure",
            name="Tool Failure Test Scenario",
            description="Testing tool failure handling",
            data=custom_data,
            failure_plans=(FailurePlan("get_order", 5, "Order DB connection timeout error"),),
        )
        repo = SimulatedCompanyRepository("customer_damaged_replacement_available")
        repo._scenario = scenario_def
        controller = AgentController(
            ToolRegistry(repo),
            EvidenceBasedDecisionProvider(),
            action_registry=ActionRegistry(repo, Decimal("50000")),
        )
        goal = "My laptop stand arrived damaged in order ORD-9002."
        state = controller.run(goal)
        self.assertEqual(state.status, "completed")
        self.assertEqual(state.customer_case.status, "ESCALATED")
        self.assertTrue(len(state.failures) > 0)
        self.assertTrue(any("escalate_customer_case" in a for a in state.actions))

    def test_06_no_unnecessary_tools(self):
        """TEST 6: Simple cancellation goal -> agent does NOT call irrelevant tools."""
        repo = SimulatedCompanyRepository("customer_replacement_out_of_stock_adapts_refund")
        controller = AgentController(
            ToolRegistry(repo),
            EvidenceBasedDecisionProvider(),
            action_registry=ActionRegistry(repo, Decimal("50000")),
        )
        goal = "I want to cancel my order ORD-9003."
        state = controller.run(goal)

        called_tools = {entry.tool_call.name for entry in state.tool_history}
        # Verify it did not call irrelevant tools
        irrelevant_tools = {"get_customer_inventory", "get_supplier_status", "get_recent_deployments", "get_service_health", "get_revenue_metrics"}
        for t in irrelevant_tools:
            self.assertNotIn(t, called_tools, f"Agent called irrelevant tool '{t}' for a simple order cancellation.")

    def test_07_llm_decision_used_and_recorded(self):
        """LLM TEST A: Verify LLM decision is used and recorded as event_type 'llm_decision'."""
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = [
            LLMResponse(content="Inspecting order ORD-9002", tool_call=ToolCall(name="get_order", arguments={"order_id": "ORD-9002"})),
            LLMResponse(content="Checking eligibility", tool_call=ToolCall(name="check_customer_resolution_eligibility", arguments={"order_id": "ORD-9002", "resolution_type": "replacement"})),
            LLMResponse(content="Proposing replacement", tool_call=ToolCall(name="create_replacement", arguments={"order_id": "ORD-9002", "customer_id": "CUST-801", "product_id": "PR-200", "quantity": 1, "reason": "Damaged"})),
            LLMResponse(content="Finished", tool_call=ToolCall(name="finish_investigation", arguments={"root_cause": "Replacement unit dispatched", "confidence": "high", "summary": "Resolved"})),
        ]
        provider = LLMDecisionProvider(mock_llm)
        controller = AgentController(self.tool_registry, provider, action_registry=self.action_registry)
        state = controller.run("My laptop stand arrived damaged in order ORD-9002.")

        llm_events = [e for e in state.events if e.event_type == "llm_decision"]
        self.assertTrue(len(llm_events) > 0, "LLM decision events were not recorded under 'llm_decision' type.")
        self.assertEqual(state.customer_case.status, "RESOLVED")

    def test_08_llm_malformed_output_falls_back(self):
        """LLM TEST B: Malformed LLM output falls back safely to rule-based decision provider."""
        mock_llm = MagicMock()
        # Returns malformed object that raises error when parsed
        mock_llm.complete.side_effect = Exception("LLM connection timeout error")

        provider = LLMDecisionProvider(mock_llm)
        controller = AgentController(self.tool_registry, provider, action_registry=self.action_registry)
        state = controller.run("My laptop stand arrived damaged in order ORD-9002. I want a replacement.")

        # Should fall back to rule-based provider and still reach completion/resolution
        self.assertEqual(state.status, "completed")
        self.assertEqual(state.customer_case.status, "RESOLVED")
        self.assertTrue(any("create_replacement" in a for a in state.actions))
        self.assertTrue(any("Falling back to rule-based decision engine" in e.summary for e in state.events))

    def test_09_llm_unknown_tool_rejected(self):
        """LLM TEST C: Unknown tool proposed by LLM is rejected and falls back safely."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = LLMResponse(
            content="Attempting magic fix",
            tool_call=ToolCall(name="non_existent_magic_tool", arguments={}),
        )

        provider = LLMDecisionProvider(mock_llm)
        controller = AgentController(self.tool_registry, provider, action_registry=self.action_registry)
        state = controller.run("My laptop stand arrived damaged in order ORD-9002.")

        # Invalid tool causes ValueError in LLMDecisionProvider -> triggers fallback to EvidenceBasedDecisionProvider
        self.assertEqual(state.status, "completed")
        self.assertEqual(state.customer_case.status, "RESOLVED")

    def test_10_llm_high_risk_approval_gating_cannot_be_bypassed(self):
        """LLM TEST D: High-risk action proposed by LLM is gated by approval; LLM cannot bypass backend permissions."""
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = [
            LLMResponse(content="Inspecting order ORD-9002", tool_call=ToolCall(name="get_order", arguments={"order_id": "ORD-9002"})),
            LLMResponse(content="Checking refund eligibility", tool_call=ToolCall(name="check_customer_resolution_eligibility", arguments={"order_id": "ORD-9002", "resolution_type": "refund"})),
            # Propose high-value refund (₹6,500 >= threshold ₹5,000)
            LLMResponse(content="Issuing refund", tool_call=ToolCall(name="issue_refund", arguments={"order_id": "ORD-9002", "customer_id": "CUST-801", "amount_inr": "6500.0", "reason": "High-value item refund"})),
        ]

        # Set threshold to ₹5,000 so ₹6,500 refund triggers high-risk approval
        action_reg = ActionRegistry(self.repo, Decimal("5000.0"))
        provider = LLMDecisionProvider(mock_llm)
        controller = AgentController(self.tool_registry, provider, action_registry=action_reg)
        state = controller.run("I want a refund for order ORD-9002.")

        # Backend MUST pause and require human approval, ignoring any LLM attempts to auto-execute
        self.assertEqual(state.status, "awaiting_approval")
        self.assertEqual(state.customer_case.status, "AWAITING_APPROVAL")
        self.assertIsNotNone(state.pending_action)
        self.assertEqual(state.pending_action.action, "issue_refund")
        self.assertEqual(state.pending_action.permission_level, "high_risk")


if __name__ == "__main__":
    unittest.main()
