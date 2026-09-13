"""Tests proving dynamic evidence-driven adaptation for PS5 customer resolution scenarios."""

from decimal import Decimal
import unittest

from backend.agent.controller import AgentController
from backend.agent.decisions import EvidenceBasedDecisionProvider
from backend.data.database import SimulatedCompanyRepository
from backend.tools.actions import ActionRegistry
from backend.tools.registry import ToolRegistry


class DynamicAgentAdaptationTests(unittest.TestCase):
    def _create_controller(self, scenario_key: str = "inventory_supplier_failure", threshold: Decimal = Decimal("5000")):
        repo = SimulatedCompanyRepository(scenario_key)
        tool_reg = ToolRegistry(repo)
        action_reg = ActionRegistry(repo, threshold)
        decision_provider = EvidenceBasedDecisionProvider()
        return AgentController(tool_reg, decision_provider, action_registry=action_reg), repo

    def test_example_a_damaged_product_replacement_flow(self) -> None:
        controller, repo = self._create_controller()
        goal = "Customer CUST-801 received defective laptop stand in order ORD-9002. Resolve the issue by replacement."
        state = controller.run(goal)

        self.assertEqual(state.status, "completed")
        self.assertIsNotNone(state.final_result)
        self.assertIn("create_replacement", [p.action for p in state.action_proposals])
        self.assertTrue(any("create_replacement" in a for a in state.actions))
        self.assertEqual(repo.get_order("ORD-9002")["replacement_state"], "completed")

    def test_example_b_out_of_stock_replacement_adapts_to_refund(self) -> None:
        controller, repo = self._create_controller()
        goal = "Customer CUST-802 requested replacement for order ORD-9003."
        state = controller.run(goal)

        self.assertEqual(state.status, "completed")
        self.assertIsNotNone(state.final_result)

        # Agent should have evaluated replacement, detected out-of-stock block, dynamically adapted to refund, and issued refund!
        proposals = [p.action for p in state.action_proposals]
        self.assertIn("issue_refund", proposals)
        self.assertTrue(any("issue_refund" in a for a in state.actions))
        self.assertEqual(repo.get_order("ORD-9003")["status"], "refunded")

    def test_example_c_shipped_order_cancellation_adapts_to_safe_escalation(self) -> None:
        controller, repo = self._create_controller()
        goal = "Customer CUST-803 requested cancellation for shipped order ORD-9004."
        state = controller.run(goal)

        self.assertEqual(state.status, "completed")
        self.assertIsNotNone(state.final_result)

        # Agent should have detected post-dispatch cancellation restriction and adapted by escalating to human agent safely!
        proposals = [p.action for p in state.action_proposals]
        self.assertIn("escalate_customer_case", proposals)
        self.assertTrue(any("escalate_customer_case" in a for a in state.actions))

    def test_example_d_high_value_refund_pauses_for_approval_and_resumes(self) -> None:
        controller, repo = self._create_controller(threshold=Decimal("5000"))
        goal = "Customer CUST-801 requested refund for damaged order ORD-9002."
        state = controller.run(goal)

        # High value refund (₹6,500 >= ₹5,000) MUST pause for human approval
        self.assertEqual(state.status, "awaiting_approval")
        self.assertIsNotNone(state.pending_action)
        self.assertEqual(state.pending_action.action, "issue_refund")
        self.assertEqual(state.pending_action.permission_level, "high_risk")

        # Resume after approval
        resumed_state = controller.resume_after_approval(state, approved=True)
        self.assertEqual(resumed_state.status, "completed")
        self.assertEqual(repo.get_order("ORD-9002")["status"], "refunded")


if __name__ == "__main__":
    unittest.main()
