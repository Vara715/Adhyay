"""Tests proving proper PS5 customer case resolution state transitions and anti-false-resolved enforcement."""

from decimal import Decimal
import unittest
from unittest.mock import MagicMock

from backend.agent.controller import AgentController
from backend.agent.decisions import EvidenceBasedDecisionProvider
from backend.data.database import SimulatedCompanyRepository
from backend.models.actions import ActionProposal, VerificationOutcome
from backend.tools.actions import ActionRegistry
from backend.tools.registry import ToolRegistry


class CustomerCaseStateTests(unittest.TestCase):
    def _create_controller(self, scenario_key: str = "inventory_supplier_failure", threshold: Decimal = Decimal("5000")):
        repo = SimulatedCompanyRepository(scenario_key)
        tool_reg = ToolRegistry(repo)
        action_reg = ActionRegistry(repo, threshold)
        decision_provider = EvidenceBasedDecisionProvider()
        return AgentController(tool_reg, decision_provider, action_registry=action_reg), repo, action_reg

    def test_customer_case_fields_and_initialization(self) -> None:
        controller, repo, _ = self._create_controller()
        goal = "Customer CUST-801 requested refund for damaged order ORD-9002."
        state = controller.run(goal)

        self.assertIsNotNone(state.customer_case)
        case = state.customer_case
        self.assertEqual(case.customer_id, "CUST-801")
        self.assertEqual(case.order_id, "ORD-9002")
        self.assertEqual(case.case_id, "CASE-ORD-9002")
        self.assertEqual(case.requested_resolution, "refund")
        self.assertEqual(case.original_goal, goal)

    def test_resolved_requires_successful_verification(self) -> None:
        """CRITICAL RULE: System MUST NOT mark a case RESOLVED merely because an action was attempted."""
        controller, repo, action_reg = self._create_controller()
        goal = "Customer CUST-801 received defective laptop stand in order ORD-9002. Resolve the issue by replacement."
        
        # Run normal flow to completion
        state = controller.run(goal)

        self.assertEqual(state.status, "completed")
        self.assertIsNotNone(state.customer_case)
        self.assertEqual(state.customer_case.status, "RESOLVED")
        self.assertIn("create_replacement", state.customer_case.actions[0])
        self.assertTrue(len(state.customer_case.verification_results) > 0)
        self.assertIn("verified", state.customer_case.verification_results[0])

    def test_prevent_false_resolved_on_failed_verification(self) -> None:
        """CRITICAL RULE: Verification failure MUST prevent case from becoming RESOLVED."""
        controller, repo, action_reg = self._create_controller()
        goal = "Customer CUST-801 received defective laptop stand in order ORD-9002. Resolve the issue by replacement."

        # Mock ActionRegistry verify to fail!
        original_verify = action_reg.verify
        def mock_failing_verify(proposal, baseline):
            return VerificationOutcome(
                status="failed",
                detail="Simulated verification failure: Inventory stock was not updated in system of record.",
                before=baseline,
                after={},
            )
        action_reg.verify = mock_failing_verify

        state = controller.run(goal)

        # The case MUST NOT be RESOLVED!
        self.assertIsNotNone(state.customer_case)
        self.assertNotEqual(state.customer_case.status, "RESOLVED")
        self.assertEqual(state.customer_case.status, "FAILED")
        self.assertTrue(len(state.customer_case.unresolved_issues) > 0)
        self.assertIn("verification failure", state.customer_case.unresolved_issues[0].lower())

    def test_prevent_false_resolved_on_inconclusive_verification(self) -> None:
        """CRITICAL RULE: Inconclusive verification MUST prevent case from becoming RESOLVED."""
        controller, repo, action_reg = self._create_controller()
        goal = "Customer CUST-801 received defective laptop stand in order ORD-9002. Resolve the issue by replacement."

        def mock_inconclusive_verify(proposal, baseline):
            return VerificationOutcome(
                status="inconclusive",
                detail="Simulated verification warning: State change unconfirmed.",
                before=baseline,
                after={},
            )
        action_reg.verify = mock_inconclusive_verify

        state = controller.run(goal)

        # The case MUST NOT be RESOLVED!
        self.assertIsNotNone(state.customer_case)
        self.assertNotEqual(state.customer_case.status, "RESOLVED")
        self.assertEqual(state.customer_case.status, "FAILED")
        self.assertTrue(len(state.customer_case.unresolved_issues) > 0)

    def test_awaiting_approval_status(self) -> None:
        """High-risk action MUST pause case in AWAITING_APPROVAL status."""
        controller, repo, _ = self._create_controller(threshold=Decimal("5000"))
        goal = "Customer CUST-801 requested refund for damaged order ORD-9002."
        state = controller.run(goal)

        self.assertEqual(state.status, "awaiting_approval")
        self.assertIsNotNone(state.customer_case)
        self.assertEqual(state.customer_case.status, "AWAITING_APPROVAL")

    def test_escalated_status_on_policy_restriction(self) -> None:
        """Shipped order cancellation MUST transition case to ESCALATED status."""
        controller, repo, _ = self._create_controller()
        goal = "Customer CUST-803 requested cancellation for shipped order ORD-9004."
        state = controller.run(goal)

        self.assertEqual(state.status, "completed")
        self.assertIsNotNone(state.customer_case)
        self.assertEqual(state.customer_case.status, "ESCALATED")
        self.assertIsNotNone(state.customer_case.escalation_reason)


if __name__ == "__main__":
    unittest.main()
