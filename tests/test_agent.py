"""Deterministic unit tests for the Stage 4 single-controller loop."""

import unittest

from backend.agent.controller import AgentController
from backend.agent.decisions import EvidenceBasedDecisionProvider
from backend.data.database import SimulatedCompanyRepository
from backend.models.agent import AgentDecision
from backend.models.agent import AgentState
from backend.models.tools import ToolCall
from backend.tools.registry import ToolRegistry


class RepeatingProvider:
    def decide(self, state, tools):
        return AgentDecision(
            kind="tool", current_objective="Keep collecting revenue data.", hypothesis="Unchanged.",
            reasoning="Test repetition.", tool_call=ToolCall(name="get_revenue_metrics"),
        )


class MalformedProvider:
    def decide(self, state, tools):
        return {"kind": "tool", "current_objective": "Broken"}


class AgentControllerTests(unittest.TestCase):
    def _controller(self, scenario: str, provider=None, **options):
        return AgentController(
            ToolRegistry(SimulatedCompanyRepository(scenario)),
            provider or EvidenceBasedDecisionProvider(),
            **options,
        )

    def test_inventory_investigation_adapts_and_completes_read_only(self) -> None:
        state = self._controller("inventory_supplier_failure").run("Revenue dropped significantly today. Investigate why.")
        tool_names = [entry.tool_call.name for entry in state.tool_history]
        self.assertEqual(state.status, "completed")
        self.assertIn("get_inventory_status", tool_names)
        self.assertIn("get_system_logs", tool_names)
        self.assertIn("get_supplier_status", tool_names)
        self.assertTrue(any("temporarily unavailable" in failure for failure in state.failures))
        self.assertIn("supplier shipment", state.final_result.conclusion)
        self.assertEqual(state.actions, [])
        self.assertEqual(state.final_result.actions_executed, [])

    def test_step_limit_stops_repeating_decisions(self) -> None:
        state = self._controller("payment_failure", RepeatingProvider(), max_steps=2).run("Investigate revenue.")
        self.assertEqual(state.status, "step_limit_reached")
        self.assertEqual(len(state.tool_history), 2)

    def test_payment_evidence_takes_a_different_path_from_inventory(self) -> None:
        state = self._controller("payment_failure").run("Revenue dropped; investigate.")
        tool_names = [entry.tool_call.name for entry in state.tool_history]
        self.assertEqual(state.status, "completed")
        self.assertIn("get_payment_status", tool_names)
        self.assertNotIn("get_inventory_status", tool_names)
        self.assertIn("payment failures", state.final_result.conclusion)

    def test_service_evidence_leads_to_deployment_verification(self) -> None:
        state = self._controller("deployment_service_failure").run("Revenue dropped; investigate.")
        tool_names = [entry.tool_call.name for entry in state.tool_history]
        self.assertEqual(state.status, "completed")
        self.assertIn("get_service_health", tool_names)
        self.assertIn("get_recent_deployments", tool_names)
        self.assertIn("get_system_logs", tool_names)
        self.assertIn("deployment", state.final_result.conclusion)

    def test_goal_wording_changes_the_initial_tool_choice(self) -> None:
        registry = ToolRegistry(SimulatedCompanyRepository("payment_failure"))
        provider = EvidenceBasedDecisionProvider()
        decision = provider.decide(AgentState(original_goal="Payment gateway failures are increasing."), registry.discover())
        self.assertEqual(decision.tool_call.name, "get_payment_status")

    def test_policy_never_selects_a_tool_outside_discovery_metadata(self) -> None:
        registry = ToolRegistry(SimulatedCompanyRepository("payment_failure"))
        provider = EvidenceBasedDecisionProvider()
        revenue_only = [tool for tool in registry.discover() if tool.name == "get_revenue_metrics"]
        decision = provider.decide(AgentState(original_goal="Payment gateway failures are increasing."), revenue_only)
        self.assertEqual(decision.tool_call.name, "get_revenue_metrics")

    def test_timeout_stops_before_a_tool_call(self) -> None:
        controller = self._controller("payment_failure", timeout_seconds=1e-12)
        state = controller.run("Investigate revenue.")
        self.assertEqual(state.status, "timed_out")
        self.assertEqual(state.tool_history, [])

    def test_malformed_provider_response_fails_safely(self) -> None:
        state = self._controller("payment_failure", MalformedProvider()).run("Investigate revenue.")
        self.assertEqual(state.status, "failed")
        self.assertIn("Malformed decision response", state.final_result.conclusion)

    def test_blank_goal_fails_safely(self) -> None:
        state = self._controller("payment_failure").run("   ")
        self.assertEqual(state.status, "failed")
        self.assertIn("non-empty", state.final_result.conclusion)


if __name__ == "__main__":
    unittest.main()
