"""Deterministic tests for failure injection, adaptation, and public execution events."""

import unittest
from typing import get_args

from backend.agent.controller import AgentController
from backend.agent.decisions import EvidenceBasedDecisionProvider
from backend.data.database import SimulatedCompanyRepository
from backend.models.events import EventType
from backend.models.agent import AgentDecision
from backend.models.tools import ToolCall
from backend.tools.registry import ToolRegistry


class RepeatingProvider:
    def decide(self, state, tools):
        return AgentDecision(
            kind="tool",
            current_objective="Repeat a test request.",
            hypothesis="Unchanged.",
            reasoning="Test-only repeated decision.",
            tool_call=ToolCall(name="get_revenue_metrics"),
        )


class AdaptationTests(unittest.TestCase):
    @staticmethod
    def _run(scenario: str, provider=None, **options):
        return AgentController(
            ToolRegistry(SimulatedCompanyRepository(scenario)),
            provider or EvidenceBasedDecisionProvider(),
            **options,
        ).run("Revenue dropped significantly today. Investigate why.")

    def test_unavailable_tool_recovers_without_inventing_data(self) -> None:
        state = self._run("inventory_supplier_failure")
        inventory_entry = next(entry for entry in state.tool_history if entry.result.tool_name == "get_inventory_status")
        event_types = [event.event_type for event in state.events]
        self.assertFalse(inventory_entry.result.ok)
        self.assertEqual(inventory_entry.result.data, {})
        self.assertIn("simulated_service_unavailable", inventory_entry.result.error.code)
        self.assertIn("tool_error", event_types)
        self.assertIn("adaptation", event_types)
        self.assertIn("get_system_logs", [entry.tool_call.name for entry in state.tool_history])
        self.assertNotIn("on hand", state.final_result.conclusion.lower())

    def test_contradiction_revises_hypothesis_and_uses_logs(self) -> None:
        state = self._run("deployment_service_failure")
        summaries = [event.summary for event in state.events if event.event_type == "adaptation"]
        hypotheses = [event.summary for event in state.events if event.event_type == "hypothesis_update"]
        self.assertTrue(any("contradictory_evidence" in summary for summary in summaries))
        self.assertGreaterEqual(len(hypotheses), 3)
        self.assertIn("deployment-related service failure", state.current_hypothesis.lower())
        self.assertIn("get_system_logs", [entry.tool_call.name for entry in state.tool_history])

    def test_stale_data_triggers_corroboration_before_completion(self) -> None:
        state = self._run("misleading_initial_hypothesis")
        summaries = [event.summary for event in state.events if event.event_type == "adaptation"]
        self.assertTrue(any("stale_data" in summary for summary in summaries))
        self.assertIn("get_system_logs", [entry.tool_call.name for entry in state.tool_history])
        self.assertEqual(state.status, "completed")

    def test_incomplete_data_is_structured_and_nonfatal(self) -> None:
        result = ToolRegistry(SimulatedCompanyRepository("payment_failure")).run("get_payment_status")
        self.assertTrue(result.ok)
        self.assertEqual(result.warnings[0].code, "incomplete_data")

    def test_action_failure_is_representable_without_executing_an_action(self) -> None:
        failure = SimulatedCompanyRepository("deployment_service_failure").get_action_failure("rollback_deployment")
        self.assertEqual(failure.code, "simulated_action_failed")
        self.assertIsNone(SimulatedCompanyRepository("deployment_service_failure").get_action_failure("create_support_ticket"))

    def test_maximum_step_protection_remains_active(self) -> None:
        state = self._run("payment_failure", RepeatingProvider(), max_steps=2)
        self.assertEqual(state.status, "step_limit_reached")
        self.assertEqual(len(state.tool_history), 2)

    def test_event_type_contract_includes_future_action_and_verification_events(self) -> None:
        self.assertTrue({
            "decision", "tool_call", "tool_result", "tool_error", "hypothesis_update", "adaptation",
            "action_proposed", "approval_required", "action_executed", "verification", "completed",
        }.issubset(set(get_args(EventType))))


if __name__ == "__main__":
    unittest.main()
