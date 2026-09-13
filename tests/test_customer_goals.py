"""Unit tests for Step 4 natural-language customer goal interpretation, goal vs resolution separation,

unsupported requests, and rule-based / LLM decision handling."""

import unittest
from decimal import Decimal
from unittest.mock import MagicMock

from backend.agent.controller import AgentController
from backend.agent.decisions import EvidenceBasedDecisionProvider, LLMDecisionProvider
from backend.data.database import SimulatedCompanyRepository
from backend.models.agent import CustomerCase
from backend.models.llm import LLMResponse
from backend.models.tools import ToolCall
from backend.tools.actions import ActionRegistry
from backend.tools.registry import ToolRegistry


class TestCustomerGoals(unittest.TestCase):
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

    def test_01_damaged_product_replacement_request(self):
        """1. Damaged product + replacement request."""
        goal = "My laptop stand arrived damaged in order ORD-9002. I want a replacement."
        state = self.controller.run(goal)
        self.assertEqual(state.status, "completed")
        self.assertIsNotNone(state.customer_case)
        self.assertEqual(state.customer_case.status, "RESOLVED")
        self.assertEqual(state.customer_case.original_goal, goal)
        self.assertEqual(state.customer_case.requested_resolution, "replacement")
        self.assertTrue(any("create_replacement" in act for act in state.actions))

    def test_02_damaged_product_refund_request(self):
        """2. Damaged product + refund request."""
        goal = "I received a damaged product in order ORD-9001 and would like my money back."
        state = self.controller.run(goal)
        self.assertEqual(state.status, "completed")
        self.assertIsNotNone(state.customer_case)
        self.assertEqual(state.customer_case.status, "RESOLVED")
        self.assertEqual(state.customer_case.requested_resolution, "refund")
        self.assertTrue(any("issue_refund" in act for act in state.actions))

    def test_03_cancellation_request(self):
        """3. Cancellation request on processing order."""
        repo = SimulatedCompanyRepository("customer_replacement_out_of_stock_adapts_refund")
        controller = AgentController(
            ToolRegistry(repo),
            EvidenceBasedDecisionProvider(),
            action_registry=ActionRegistry(repo, Decimal("50000")),
        )
        goal = "I want to cancel my order ORD-9003 because I no longer need it."
        state = controller.run(goal)
        self.assertEqual(state.status, "completed")
        self.assertIsNotNone(state.customer_case)
        self.assertEqual(state.customer_case.status, "RESOLVED")
        self.assertEqual(state.customer_case.requested_resolution, "cancellation")
        self.assertTrue(any("cancel_order" in act for act in state.actions))

    def test_04_generic_damaged_complaint_without_explicit_resolution(self):
        """4. Generic damaged product complaint without explicit resolution requested."""
        goal = "My order ORD-9002 arrived damaged."
        state = self.controller.run(goal)
        self.assertEqual(state.status, "completed")
        self.assertIsNotNone(state.customer_case)
        # Should not force requested_resolution to replacement before checking eligibility
        self.assertIsNone(state.customer_case.requested_resolution)
        self.assertEqual(state.customer_case.status, "RESOLVED")

    def test_05_replacement_unavailable_adapts_to_refund(self):
        """5. Replacement requested but inventory out of stock -> adapts to refund."""
        repo = SimulatedCompanyRepository("customer_replacement_out_of_stock_adapts_refund")
        controller = AgentController(
            ToolRegistry(repo),
            EvidenceBasedDecisionProvider(),
            action_registry=ActionRegistry(repo, Decimal("50000")),
        )
        goal = "My product in order ORD-9003 arrived defective. Please replace it."
        state = controller.run(goal)
        self.assertEqual(state.status, "completed")
        self.assertIsNotNone(state.customer_case)
        self.assertEqual(state.customer_case.status, "RESOLVED")
        # Goal requested replacement, but agent dynamically adapted to issue_refund after stockout!
        self.assertTrue(any("issue_refund" in act for act in state.actions))
        self.assertTrue(any("out" in item.fact.lower() or "stock" in item.fact.lower() or "refund" in item.fact.lower() for item in state.evidence))

    def test_06_refund_policy_denial_escalation(self):
        """6. Post-dispatch cancellation / refund denial policy escalation."""
        repo = SimulatedCompanyRepository("customer_refund_denied_policy_escalation")
        controller = AgentController(
            ToolRegistry(repo),
            EvidenceBasedDecisionProvider(),
            action_registry=ActionRegistry(repo, Decimal("50000")),
        )
        goal = "I want to cancel my shipped order ORD-9004."
        state = controller.run(goal)
        self.assertEqual(state.status, "completed")
        self.assertIsNotNone(state.customer_case)
        self.assertEqual(state.customer_case.status, "ESCALATED")
        self.assertTrue(any("escalate_customer_case" in act for act in state.actions))

    def test_07_unsupported_customer_request(self):
        """7. Unsupported customer request (e.g. change color of product)."""
        goal = "I want to change the color of my product in order ORD-9001."
        state = self.controller.run(goal)
        self.assertEqual(state.status, "completed")
        self.assertIsNotNone(state.customer_case)
        self.assertEqual(state.customer_case.status, "ESCALATED")
        self.assertTrue(any("escalate_customer_case" in act for act in state.actions))

    def test_08_empty_goal(self):
        """8. Empty goal handling."""
        state = self.controller.run("   ")
        self.assertEqual(state.status, "failed")
        self.assertIn("non-empty", state.failures[0].lower())

    def test_09_very_ambiguous_goal(self):
        """9. Very ambiguous goal handling."""
        goal = "I need help with something on my order ORD-9001."
        state = self.controller.run(goal)
        self.assertEqual(state.status, "completed")
        self.assertIsNotNone(state.customer_case)
        self.assertEqual(state.customer_case.status, "ESCALATED")
        self.assertTrue(any("escalate_customer_case" in act for act in state.actions))

    def test_10_llm_goal_interpretation(self):
        """10. LLM goal interpretation test with mocked LLM client."""
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = [
            # Step 1: LLM decides to check order
            LLMResponse(
                content="Checking order details for ORD-9002.",
                tool_call=ToolCall(name="get_order", arguments={"order_id": "ORD-9002"}),
            ),
            # Step 2: LLM decides to check eligibility
            LLMResponse(
                content="Checking replacement eligibility.",
                tool_call=ToolCall(name="check_customer_resolution_eligibility", arguments={"order_id": "ORD-9002", "resolution_type": "replacement"}),
            ),
            # Step 3: LLM decides to create replacement
            LLMResponse(
                content="Replacement is eligible. Dispatching replacement unit.",
                tool_call=ToolCall(name="create_replacement", arguments={
                    "order_id": "ORD-9002", "customer_id": "CUST-801", "product_id": "PR-200", "quantity": 1, "reason": "Damaged unit replacement",
                }),
            ),
            # Step 4: LLM decides to finish
            LLMResponse(
                content="Finished investigation.",
                tool_call=ToolCall(name="finish_investigation", arguments={
                    "root_cause": "Replacement dispatched and verified.", "confidence": "high", "summary": "Customer issue resolved.",
                }),
            ),
        ]
        provider = LLMDecisionProvider(mock_llm)
        controller = AgentController(
            self.tool_registry,
            provider,
            action_registry=self.action_registry,
        )
        goal = "My laptop stand arrived damaged. Can you replace it?"
        state = controller.run(goal)
        self.assertEqual(state.status, "completed")
        self.assertEqual(state.customer_case.status, "RESOLVED")

    def test_11_rule_based_fallback_goal_handling(self):
        """11. Rule-based fallback handles natural language goals without hardcoded keyword scripts."""
        goal = "Please check my order ORD-9002 because the item arrived broken."
        state = self.controller.run(goal)
        self.assertEqual(state.status, "completed")
        self.assertIsNotNone(state.customer_case)
        # Empirical evidence drives decision, not direct keyword script
        self.assertEqual(state.customer_case.status, "RESOLVED")
        self.assertTrue(any("create_replacement" in act for act in state.actions))


if __name__ == "__main__":
    unittest.main()
