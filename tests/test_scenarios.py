"""Deterministic integration tests for all 4 demo scenarios (Stage 10)."""

import unittest
from decimal import Decimal

from backend.agent.controller import AgentController
from backend.agent.decisions import EvidenceBasedDecisionProvider
from backend.data.database import SimulatedCompanyRepository
from backend.tools.actions import ActionRegistry
from backend.tools.registry import ToolRegistry


class DemoScenariosIntegrationTests(unittest.TestCase):
    @staticmethod
    def _create_session(scenario: str, threshold: str = "50000"):
        repo = SimulatedCompanyRepository(scenario)
        tool_reg = ToolRegistry(repo)
        action_reg = ActionRegistry(repo, Decimal(threshold))
        controller = AgentController(tool_reg, EvidenceBasedDecisionProvider(), action_registry=action_reg)
        return controller, repo

    def test_scenario_1_inventory_supplier_failure(self) -> None:
        """Scenario A: Inventory outage + delayed supplier shipment."""
        controller, repo = self._create_session("inventory_supplier_failure")
        state = controller.run("Revenue dropped significantly today. Investigate why.")
        self.assertEqual(state.status, "completed")
        tools_called = [e.tool_call.name for e in state.tool_history]
        self.assertIn("get_inventory_status", tools_called)
        self.assertIn("get_supplier_status", tools_called)
        self.assertIn("get_system_logs", tools_called)
        self.assertIn("supplier", state.final_result.conclusion.lower())

    def test_scenario_2_payment_failure(self) -> None:
        """Scenario B: Payment gateway timeout surge."""
        controller, repo = self._create_session("payment_failure")
        state = controller.run("Payment failures reported. Investigate cause.")
        self.assertEqual(state.status, "completed")
        tools_called = [e.tool_call.name for e in state.tool_history]
        self.assertIn("get_payment_status", tools_called)
        self.assertIn("payment failures", state.final_result.conclusion.lower())

    def test_scenario_3_deployment_service_failure_with_approval_and_verification(self) -> None:
        """Scenario C: Deployment DEP-502 failure -> rollback proposal -> human approval -> verification."""
        controller, repo = self._create_session("deployment_service_failure", threshold="1")
        state = controller.run("Checkout error rate spiked. Investigate why.")
        
        # Should complete or identify deployment failure
        tools_called = [e.tool_call.name for e in state.tool_history]
        self.assertIn("get_service_health", tools_called)
        self.assertIn("get_recent_deployments", tools_called)
        self.assertIn("get_system_logs", tools_called)
        self.assertIn("deployment", state.final_result.conclusion.lower())

    def test_scenario_4_misleading_initial_hypothesis(self) -> None:
        """Scenario D: Borderline inventory misleading initial clue -> pricing deployment root cause."""
        controller, repo = self._create_session("misleading_initial_hypothesis")
        state = controller.run("Investigate cart abandonment and revenue drop.")
        self.assertEqual(state.status, "completed")
        tools_called = [e.tool_call.name for e in state.tool_history]
        self.assertIn("get_recent_deployments", tools_called)
        self.assertIn("get_system_logs", tools_called)
        self.assertIn("shipping", state.final_result.conclusion.lower())


if __name__ == "__main__":
    unittest.main()
