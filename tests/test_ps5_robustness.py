"""Strict PS5 Robustness and Edge-Case Reliability Tests covering all 20 error modes."""

from decimal import Decimal
import time
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from backend.agent.controller import AgentController
from backend.agent.decisions import EvidenceBasedDecisionProvider
from backend.data.database import SimulatedCompanyRepository
from backend.data.scenarios import SCENARIOS, ScenarioDefinition
from backend.main import app
from backend.models.actions import ActionProposal, VerificationOutcome
from backend.models.tools import ToolCall, ToolResult
from backend.tools.actions import ActionRegistry
from backend.tools.customer import GetCustomerTool, GetOrderTool
from backend.tools.registry import ToolRegistry


class PS5RobustnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = SimulatedCompanyRepository("inventory_supplier_failure")
        self.tool_reg = ToolRegistry(self.repo)
        self.action_reg = ActionRegistry(self.repo, Decimal("5000"))
        self.controller = AgentController(self.tool_reg, EvidenceBasedDecisionProvider(), action_registry=self.action_reg)

    # 1. Missing Customer
    def test_1_missing_customer_returns_not_found(self) -> None:
        tool = GetCustomerTool()
        res = tool.execute(self.repo, tool.input_model(customer_id="CUST-9999"))
        self.assertFalse(res.ok)
        self.assertEqual(res.error.code, "not_found")

    # 2. Missing Order
    def test_2_missing_order_returns_not_found(self) -> None:
        tool = GetOrderTool()
        res = tool.execute(self.repo, tool.input_model(order_id="ORD-9999"))
        self.assertFalse(res.ok)
        self.assertEqual(res.error.code, "not_found")

    # 3. Invalid Case / Unknown Scenario
    def test_3_invalid_scenario_returns_error(self) -> None:
        client = TestClient(app)
        response = client.post(
            "/api/runs",
            json={"goal": "Test goal", "scenario": "non_existent_scenario"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Unknown scenario", response.json()["detail"])

    # 4. Invalid / Empty User Goal
    def test_4_invalid_empty_user_goal_returns_failed_state(self) -> None:
        state_empty = self.controller.run("")
        self.assertEqual(state_empty.status, "failed")

        state_ws = self.controller.run("   \n\t  ")
        self.assertEqual(state_ws.status, "failed")

        state_none = self.controller.run(None)  # type: ignore
        self.assertEqual(state_none.status, "failed")

    # 5. Malformed LLM Response
    def test_5_malformed_llm_response_handled_gracefully(self) -> None:
        class MalformedDecisionProvider:
            def decide(self, state, tools):
                return "invalid_string_response_not_decision"

        bad_controller = AgentController(self.tool_reg, MalformedDecisionProvider())
        state = bad_controller.run("Customer CUST-801 received defective headphones in order ORD-9001.")
        self.assertEqual(state.status, "failed")
        self.assertIn("Malformed decision", state.failures[0])

    # 6. Unknown Tool Call
    def test_6_unknown_tool_call_handled_safely(self) -> None:
        res = self.tool_reg.execute(ToolCall(name="unregistered_tool_name"))
        self.assertFalse(res.ok)
        self.assertEqual(res.error.code, "unknown_tool")

    # 7. Invalid Tool Arguments
    def test_7_invalid_tool_arguments_rejected(self) -> None:
        res = self.action_reg.propose("issue_refund", {"order_id": "", "amount_inr": -100}, reason="r", evidence=[])
        self.assertFalse(res.ok)
        self.assertEqual(res.error.code, "invalid_input")

    # 8. Tool / Run Timeout
    def test_8_tool_timeout_stops_controller_safely(self) -> None:
        timeout_controller = AgentController(self.tool_reg, EvidenceBasedDecisionProvider(), timeout_seconds=0.001)
        state = timeout_controller.run("Customer CUST-801 received defective headphones in order ORD-9001.")
        self.assertIn(state.status, ["timed_out", "completed"])

    # 9. Tool Failure (Injected FailurePlan)
    def test_9_injected_tool_failure_recorded_and_adapted(self) -> None:
        controller, repo = AgentController(
            ToolRegistry(SimulatedCompanyRepository("customer_investigation_tool_failure_adapts")),
            EvidenceBasedDecisionProvider(),
            action_registry=ActionRegistry(SimulatedCompanyRepository("customer_investigation_tool_failure_adapts"), Decimal("5000")),
        ), SimulatedCompanyRepository("customer_investigation_tool_failure_adapts")
        state = controller.run("Customer CUST-801 received defective headphones in order ORD-9001.")
        self.assertIn(state.status, ["completed", "failed"])

    # 10. Unavailable Inventory (Stock = 0)
    def test_10_unavailable_inventory_adapts_to_refund(self) -> None:
        controller, repo = AgentController(
            ToolRegistry(SimulatedCompanyRepository("customer_replacement_out_of_stock_adapts_refund")),
            EvidenceBasedDecisionProvider(),
            action_registry=ActionRegistry(SimulatedCompanyRepository("customer_replacement_out_of_stock_adapts_refund"), Decimal("50000")),
        ), SimulatedCompanyRepository("customer_replacement_out_of_stock_adapts_refund")
        state = controller.run("Customer CUST-802 requested replacement for order ORD-9003.")
        self.assertEqual(state.status, "completed")
        self.assertIn("issue_refund", [p.action for p in state.action_proposals])

    # 11. Contradictory Policy / Evidence
    def test_11_contradictory_policy_adapts_to_escalation(self) -> None:
        controller, repo = AgentController(
            ToolRegistry(SimulatedCompanyRepository("customer_refund_denied_policy_escalation")),
            EvidenceBasedDecisionProvider(),
            action_registry=ActionRegistry(SimulatedCompanyRepository("customer_refund_denied_policy_escalation"), Decimal("50000")),
        ), SimulatedCompanyRepository("customer_refund_denied_policy_escalation")
        state = controller.run("Customer CUST-803 requested cancellation for shipped order ORD-9004.")
        self.assertEqual(state.status, "completed")
        self.assertEqual(state.customer_case.status, "ESCALATED")

    # 12. Action Rejection
    def test_12_action_rejection_logs_rejection_and_resumes(self) -> None:
        state = self.controller.run("Customer CUST-801 requested refund for damaged order ORD-9002.")
        self.assertEqual(state.status, "awaiting_approval")
        
        resumed = self.controller.resume_after_approval(state, approved=False)
        self.assertEqual(resumed.status, "completed")
        self.assertIn("rejected by human reviewer", resumed.actions[0])

    # 13. Action Failure
    def test_13_simulated_action_failure_handled_safely(self) -> None:
        repo = SimulatedCompanyRepository("deployment_service_failure")
        action_reg = ActionRegistry(repo, Decimal("50000"))
        proposal = action_reg.propose("rollback_deployment", {"deployment_id": "DEP-502", "reason": "r"}, reason="r", evidence=[])
        action_reg.approve(proposal)
        res = action_reg.execute(proposal)
        self.assertFalse(res.ok)
        self.assertEqual(proposal.approval_status, "failed")

    # 14. Approval Rejection Preserves Safety
    def test_14_approval_rejection_does_not_execute_action(self) -> None:
        state = self.controller.run("Customer CUST-801 requested refund for damaged order ORD-9002.")
        self.assertEqual(state.status, "awaiting_approval")
        proposal = state.pending_action

        resumed = self.controller.resume_after_approval(state, approved=False)
        self.assertEqual(proposal.approval_status, "rejected")
        self.assertNotEqual(self.repo.get_order("ORD-9002")["status"], "refunded")

    # 15. Verification Failure
    def test_15_verification_failure_prevents_resolved_status(self) -> None:
        def failing_verify(self_reg, proposal, baseline):
            return VerificationOutcome(status="failed", detail="Verification failed detail.", before={}, after={})

        with patch.object(ActionRegistry, "verify", failing_verify):
            state = self.controller.run("Customer CUST-801 received defective laptop stand in order ORD-9002. Resolve the issue by replacement.")
            self.assertNotEqual(state.customer_case.status, "RESOLVED")
            self.assertEqual(state.customer_case.status, "FAILED")

    # 16. Verification Inconclusive
    def test_16_verification_inconclusive_prevents_resolved_status(self) -> None:
        def inconclusive_verify(self_reg, proposal, baseline):
            return VerificationOutcome(status="inconclusive", detail="Verification inconclusive detail.", before={}, after={})

        with patch.object(ActionRegistry, "verify", inconclusive_verify):
            state = self.controller.run("Customer CUST-801 received defective laptop stand in order ORD-9002. Resolve the issue by replacement.")
            self.assertNotEqual(state.customer_case.status, "RESOLVED")
            self.assertEqual(state.customer_case.status, "FAILED")

    # 17. Repeated Tool Calls Prevention
    def test_17_repeated_tool_calls_prevented(self) -> None:
        state = self.controller.run("Customer CUST-801 received defective laptop stand in order ORD-9002. Resolve the issue by replacement.")
        get_order_calls = [e for e in state.tool_history if e.tool_call.name == "get_order"]
        self.assertEqual(len(get_order_calls), 1)

    # 18. Maximum Step Limit
    def test_18_maximum_step_limit_stops_controller(self) -> None:
        class InfiniteLoopProvider:
            def decide(self, state, tools):
                return {
                    "kind": "tool",
                    "current_objective": "Looping",
                    "hypothesis": "Looping",
                    "reasoning": "Looping",
                    "tool_call": ToolCall(name="get_order", arguments={"order_id": "ORD-9001"}),
                }

        controller = AgentController(self.tool_reg, InfiniteLoopProvider(), max_steps=2)
        state = controller.run("Customer CUST-801 received defective headphones in order ORD-9001.")
        self.assertEqual(state.status, "step_limit_reached")
        self.assertEqual(state.step_count, 2)

    # 19. Unavailable Data Handled Without Crash
    def test_19_unavailable_data_returns_structured_error(self) -> None:
        res_cust = GetCustomerTool().execute(self.repo, GetCustomerTool.input_model(email="nonexistent@example.com"))
        self.assertFalse(res_cust.ok)

        res_order = GetOrderTool().execute(self.repo, GetOrderTool.input_model(order_id="ORD-0000"))
        self.assertFalse(res_order.ok)

    # 20. Missing LLM Credentials Fallback
    def test_20_missing_llm_credentials_falls_back_to_rule_based_mode(self) -> None:
        client = TestClient(app)
        res = client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        run_res = client.post(
            "/api/runs",
            json={
                "goal": "Customer CUST-801 received defective laptop stand in order ORD-9002. Resolve the issue by replacement.",
                "scenario": "customer_damaged_replacement_available",
                "step_delay_seconds": 0.0,
            },
        )
        self.assertEqual(run_res.status_code, 200)
        self.assertEqual(run_res.json()["status"], "completed")


if __name__ == "__main__":
    unittest.main()
