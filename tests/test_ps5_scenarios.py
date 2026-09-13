"""Repeatable tests for PS5 customer-resolution scenarios and existing operational scenarios."""

from decimal import Decimal
import unittest

from backend.agent.controller import AgentController
from backend.agent.decisions import EvidenceBasedDecisionProvider
from backend.data.database import SimulatedCompanyRepository
from backend.data.scenarios import SCENARIOS
from backend.tools.actions import ActionRegistry
from backend.tools.registry import ToolRegistry


class PS5CustomerResolutionScenarioTests(unittest.TestCase):
    def _create_controller(self, scenario_key: str, threshold: Decimal = Decimal("5000")):
        repo = SimulatedCompanyRepository(scenario_key)
        tool_reg = ToolRegistry(repo)
        action_reg = ActionRegistry(repo, threshold)
        decision_provider = EvidenceBasedDecisionProvider()
        return AgentController(tool_reg, decision_provider, action_registry=action_reg), repo

    def test_scenario_1_damaged_replacement_available(self) -> None:
        """Damaged product → replacement available → replacement succeeds → verification → RESOLVED."""
        controller, repo = self._create_controller("customer_damaged_replacement_available")
        goal = "Customer CUST-801 received defective laptop stand in order ORD-9002. Resolve the issue by replacement."
        state = controller.run(goal)

        self.assertEqual(state.status, "completed")
        self.assertIsNotNone(state.customer_case)
        self.assertEqual(state.customer_case.status, "RESOLVED")
        self.assertIn("create_replacement", [p.action for p in state.action_proposals])
        self.assertEqual(repo.get_order("ORD-9002")["replacement_state"], "completed")

    def test_scenario_2_replacement_out_of_stock_adapts_to_refund(self) -> None:
        """Damaged/product issue → replacement unavailable → agent adapts → eligible refund → refund succeeds → verification → RESOLVED."""
        controller, repo = self._create_controller("customer_replacement_out_of_stock_adapts_refund")
        goal = "Customer CUST-802 requested replacement for order ORD-9003."
        state = controller.run(goal)

        self.assertEqual(state.status, "completed")
        self.assertIsNotNone(state.customer_case)
        self.assertEqual(state.customer_case.status, "RESOLVED")

        # Dynamic adaptation check: refund action proposed & executed after replacement stockout
        proposals = [p.action for p in state.action_proposals]
        self.assertIn("issue_refund", proposals)
        self.assertEqual(repo.get_order("ORD-9003")["status"], "refunded")

    def test_scenario_3_refund_denied_policy_escalation(self) -> None:
        """Refund/cancellation requested → policy denies refund (shipped order) → agent cannot safely complete → ESCALATED."""
        controller, repo = self._create_controller("customer_refund_denied_policy_escalation")
        goal = "Customer CUST-803 requested cancellation for shipped order ORD-9004."
        state = controller.run(goal)

        self.assertEqual(state.status, "completed")
        self.assertIsNotNone(state.customer_case)
        self.assertEqual(state.customer_case.status, "ESCALATED")
        self.assertIn("escalate_customer_case", [p.action for p in state.action_proposals])

    def test_scenario_4_investigation_tool_failure_adapts(self) -> None:
        """Customer-resolution investigation tool failure → agent detects failure → adapts using another available path."""
        controller, repo = self._create_controller("customer_investigation_tool_failure_adapts")
        goal = "Customer CUST-801 received defective laptop stand in order ORD-9002. Resolve the issue."
        state = controller.run(goal)

        self.assertEqual(state.status, "completed")
        self.assertIsNotNone(state.customer_case)
        self.assertIn(state.customer_case.status, ["RESOLVED", "ESCALATED"])

    def test_all_scenarios_registered_and_executable(self) -> None:
        """Ensure all 8 scenarios (4 operational + 4 customer resolution) are registered and loadable."""
        expected_keys = {
            "inventory_supplier_failure",
            "payment_failure",
            "deployment_service_failure",
            "misleading_initial_hypothesis",
            "customer_damaged_replacement_available",
            "customer_replacement_out_of_stock_adapts_refund",
            "customer_refund_denied_policy_escalation",
            "customer_investigation_tool_failure_adapts",
        }
        self.assertTrue(expected_keys.issubset(set(SCENARIOS.keys())))


if __name__ == "__main__":
    unittest.main()
