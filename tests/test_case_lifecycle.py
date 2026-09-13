"""Tests verifying the lifecycle of new customer-resolution cases."""

from decimal import Decimal
from time import monotonic
import unittest

from backend.agent.controller import AgentController
from backend.agent.decisions import EvidenceBasedDecisionProvider
from backend.api.runs import _build_customer_case, start_run, CreateRunRequest
from backend.data.database import SimulatedCompanyRepository
from backend.models.actions import VerificationOutcome
from backend.models.agent import AgentState, CustomerCase
from backend.tools.actions import ActionRegistry
from backend.tools.registry import ToolRegistry


class CaseLifecycleTests(unittest.TestCase):
    def _create_controller(self, scenario_key: str = "customer_investigation_tool_failure_adapts", threshold: Decimal = Decimal("5000")):
        repo = SimulatedCompanyRepository(scenario_key)
        tool_reg = ToolRegistry(repo)
        action_reg = ActionRegistry(repo, threshold)
        decision_provider = EvidenceBasedDecisionProvider()
        return AgentController(tool_reg, decision_provider, action_registry=action_reg), repo, action_reg

    def test_1_new_case_starts_open(self) -> None:
        """1. New case starts in OPEN status."""
        case = _build_customer_case("customer_damaged_replacement_available")
        self.assertEqual(case.status, "OPEN")
        self.assertIsNotNone(case.case_id)

    def test_2_new_case_is_not_resolved_before_execution(self) -> None:
        """2. New case is NOT resolved before execution starts."""
        controller, repo, _ = self._create_controller("customer_damaged_replacement_available")
        case = _build_customer_case("customer_damaged_replacement_available")
        state = AgentState(
            original_goal="Customer CUST-801 received defective laptop stand in order ORD-9002. Resolve the issue by replacement.",
            customer_case=case,
        )

        self.assertEqual(state.customer_case.status, "OPEN")
        self.assertNotEqual(state.customer_case.status, "RESOLVED")
        self.assertNotEqual(state.customer_case.status, "ESCALATED")
        self.assertNotEqual(state.customer_case.status, "FAILED")
        self.assertEqual(state.status, "running")
        self.assertEqual(len(state.tool_history), 0)

    def test_3_running_case_becomes_investigating_then_resolved(self) -> None:
        """3. Running case transitions from OPEN through INVESTIGATING to terminal status."""
        controller, repo, _ = self._create_controller("customer_investigation_tool_failure_adapts")
        goal = "Customer CUST-801 received defective headphones in order ORD-9001. Resolve the issue."
        case = controller._init_customer_case(goal)
        self.assertEqual(case.status, "OPEN")

        state = AgentState(original_goal=goal, customer_case=case)
        self.assertEqual(state.customer_case.status, "OPEN")

        controller._run_loop(state, monotonic(), step_delay=0.0)
        self.assertEqual(state.customer_case.status, "RESOLVED")

    def test_4_successful_action_and_verification_becomes_resolved(self) -> None:
        """4. Successful action + successful verification transitions status to RESOLVED."""
        controller, repo, _ = self._create_controller("customer_investigation_tool_failure_adapts")
        goal = "Customer CUST-801 received defective headphones in order ORD-9001. Resolve the issue."
        state = controller.run(goal)

        self.assertEqual(state.status, "completed")
        self.assertIsNotNone(state.customer_case)
        self.assertEqual(state.customer_case.status, "RESOLVED")
        self.assertIsNotNone(state.customer_case.final_resolution)

    def test_5_failed_verification_cannot_become_resolved(self) -> None:
        """5. Failed verification prevents case from becoming RESOLVED."""
        controller, repo, action_reg = self._create_controller("customer_investigation_tool_failure_adapts")
        goal = "Customer CUST-801 received defective headphones in order ORD-9001. Resolve the issue."

        def mock_failing_verify(proposal, baseline):
            return VerificationOutcome(
                status="failed",
                detail="Simulated failure: DB mutation mismatch.",
                before=baseline,
                after={},
            )
        action_reg.verify = mock_failing_verify

        state = controller.run(goal)

        self.assertIsNotNone(state.customer_case)
        self.assertNotEqual(state.customer_case.status, "RESOLVED")
        self.assertEqual(state.customer_case.status, "FAILED")

    def test_6_escalation_becomes_escalated(self) -> None:
        """6. Escalated action transitions case status to ESCALATED."""
        controller, repo, _ = self._create_controller("customer_refund_denied_policy_escalation")
        goal = "Customer CUST-803 requested cancellation for shipped order ORD-9004."
        state = controller.run(goal)

        self.assertEqual(state.status, "completed")
        self.assertIsNotNone(state.customer_case)
        self.assertEqual(state.customer_case.status, "ESCALATED")

    def test_7_api_start_run_initializes_open_case(self) -> None:
        """7. API start_run endpoint initializes a brand-new run with OPEN case status."""
        req = CreateRunRequest(
            goal="Customer CUST-801 received defective headphones in order ORD-9001. Resolve the issue.",
            scenario="customer_investigation_tool_failure_adapts",
            approval_threshold_inr=Decimal("5000"),
            step_delay_seconds=1.0,
        )
        state = start_run(req)

        self.assertIsNotNone(state.customer_case)
        self.assertIn(state.customer_case.status, ["OPEN", "INVESTIGATING"])
        self.assertNotEqual(state.customer_case.status, "RESOLVED")
        self.assertEqual(state.status, "running")

    def test_8_create_case_without_auto_start(self) -> None:
        """8. Creating a case with auto_start=False leaves case in OPEN status with 0 steps executed."""
        req = CreateRunRequest(
            goal="Customer CUST-801 received defective laptop stand in order ORD-9002.",
            scenario="customer_damaged_replacement_available",
            approval_threshold_inr=Decimal("5000"),
            step_delay_seconds=0.6,
            auto_start=False,
        )
        state = start_run(req)

        self.assertIsNotNone(state.customer_case)
        self.assertEqual(state.customer_case.status, "OPEN")
        self.assertEqual(state.step_count, 0)
        self.assertEqual(len(state.tool_history), 0)


if __name__ == "__main__":
    unittest.main()
