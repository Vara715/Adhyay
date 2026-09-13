"""Unit tests for Step 6 proving explicit agent adaptation, original goal preservation,

stockout adaptation, tool failure adaptation, policy block adaptation, verification failure handling, and retry loop prevention."""

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


class TestExplicitAdaptation(unittest.TestCase):
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

    def test_01_stockout_adaptation_preserves_goal(self):
        """TEST 1: Stockout adaptation preserves original_goal, sets adaptation state, executes refund & verifies."""
        repo = SimulatedCompanyRepository("customer_replacement_out_of_stock_adapts_refund")
        controller = AgentController(
            ToolRegistry(repo),
            EvidenceBasedDecisionProvider(),
            action_registry=ActionRegistry(repo, Decimal("50000")),
        )
        goal = "I received a damaged product in order ORD-9003 and want a replacement."
        state = controller.run(goal)

        # 1. Original goal preserved
        self.assertEqual(state.original_goal, goal)
        self.assertEqual(state.customer_case.original_goal, goal)
        # 2. Adaptation state recorded
        self.assertTrue(state.adaptation_required)
        self.assertTrue(state.adaptation_count >= 1)
        self.assertIsNotNone(state.adaptation_reason)
        # 3. Action executed & verified
        self.assertEqual(state.status, "completed")
        self.assertEqual(state.customer_case.status, "RESOLVED")
        self.assertTrue(any("issue_refund" in a for a in state.actions))
        # 4. Replacement was NOT repeatedly retried
        replacement_attempts = [p for p in state.action_proposals if p.action == "create_replacement"]
        self.assertEqual(len(replacement_attempts), 0)

    def test_02_tool_failure_adaptation(self):
        """TEST 2: Tool failure -> recorded in state, adaptation triggered, no fabricated data, safely escalates."""
        custom_data = _base_data()
        scenario_def = ScenarioDefinition(
            key="custom_tool_fail",
            name="Tool Failure Scenario",
            description="Testing tool failure adaptation",
            data=custom_data,
            failure_plans=(FailurePlan("get_order", 5, "Database read timeout"),),
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
        self.assertTrue(state.adaptation_required)
        self.assertTrue(len(state.failures) > 0)
        self.assertIn("Database read timeout", state.failures[0])
        # Ensure status is NOT RESOLVED with fabricated order data
        self.assertNotEqual(state.customer_case.status, "RESOLVED")

    def test_03_policy_block_adaptation(self):
        """TEST 3: Prohibited action (cancellation post-dispatch) -> adaptation recorded, prohibited action NOT executed."""
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
        self.assertFalse(any("cancel_order" in a for a in state.actions))
        self.assertTrue(any("escalate_customer_case" in a for a in state.actions))

    def test_04_verification_failure_prevents_resolved(self):
        """TEST 4: Action execution where verification fails -> prevents RESOLVED status, sets FAILED state."""
        # Mock action registry verify to return failed outcome
        repo = SimulatedCompanyRepository("customer_damaged_replacement_available")
        action_reg = ActionRegistry(repo, Decimal("50000"))

        mock_outcome = MagicMock()
        mock_outcome.status = "failed"
        mock_outcome.detail = "Post-action database state check failed: replacement record missing."
        action_reg.verify = MagicMock(return_value=mock_outcome)

        controller = AgentController(
            ToolRegistry(repo),
            EvidenceBasedDecisionProvider(),
            action_registry=action_reg,
        )
        goal = "My laptop stand arrived damaged in order ORD-9002. I want a replacement."
        state = controller.run(goal)

        # Verification failure MUST prevent RESOLVED status!
        self.assertNotEqual(state.customer_case.status, "RESOLVED")
        self.assertEqual(state.customer_case.status, "FAILED")
        self.assertTrue(state.adaptation_required)
        self.assertTrue(len(state.verification_notes) > 0)

    def test_05_retry_loop_prevention(self):
        """TEST 5: Ensure step count is bounded and agent does not loop infinitely on repeated decisions."""
        repo = SimulatedCompanyRepository("customer_damaged_replacement_available")
        controller = AgentController(
            ToolRegistry(repo),
            EvidenceBasedDecisionProvider(),
            action_registry=ActionRegistry(repo, Decimal("50000")),
            max_steps=5,
        )
        goal = "My laptop stand arrived damaged in order ORD-9002."
        state = controller.run(goal)

        # Step count must be bounded <= max_steps
        self.assertLessEqual(state.step_count, 5)
        # Should reach terminal state cleanly without crashing
        self.assertIn(state.status, ("completed", "step_limit_reached", "failed"))

    def test_06_original_goal_preservation_under_adaptation(self):
        """TEST 6: original_goal remains 100% unchanged across multi-step adaptation, while current_objective updates."""
        repo = SimulatedCompanyRepository("customer_replacement_out_of_stock_adapts_refund")
        controller = AgentController(
            ToolRegistry(repo),
            EvidenceBasedDecisionProvider(),
            action_registry=ActionRegistry(repo, Decimal("50000")),
        )
        initial_goal = "I received a damaged product in order ORD-9003 and want a replacement."
        state = controller.run(initial_goal)

        # 1. Goal preserved strictly
        self.assertEqual(state.original_goal, initial_goal)
        self.assertEqual(state.customer_case.original_goal, initial_goal)
        # 2. Objective updated dynamically to adapted plan
        self.assertNotEqual(state.current_objective, initial_goal)
        self.assertTrue(state.adaptation_count >= 1)


if __name__ == "__main__":
    unittest.main()
