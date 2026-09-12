"""Robustness and edge-case reliability tests for Stage 11."""

import unittest
from decimal import Decimal

from backend.agent.controller import AgentController
from backend.agent.decisions import EvidenceBasedDecisionProvider
from backend.data.database import SimulatedCompanyRepository
from backend.models.agent import AgentState
from backend.models.tools import ToolCall
from backend.tools.actions import ActionRegistry
from backend.tools.registry import ToolRegistry


class RobustnessTests(unittest.TestCase):
    @staticmethod
    def _create_session(scenario: str = "payment_failure"):
        repo = SimulatedCompanyRepository(scenario)
        tool_reg = ToolRegistry(repo)
        action_reg = ActionRegistry(repo, Decimal("50000"))
        controller = AgentController(tool_reg, EvidenceBasedDecisionProvider(), action_registry=action_reg)
        return controller, repo

    def test_empty_string_goal_returns_failed_state(self) -> None:
        controller, _ = self._create_session()
        state = controller.run("")
        self.assertEqual(state.status, "failed")
        self.assertIn("non-empty", state.failures[0].lower())

    def test_whitespace_only_goal_returns_failed_state(self) -> None:
        controller, _ = self._create_session()
        state = controller.run("   \n\t  ")
        self.assertEqual(state.status, "failed")
        self.assertIn("non-empty", state.failures[0].lower())

    def test_non_string_goal_returns_failed_state(self) -> None:
        controller, _ = self._create_session()
        state = controller.run(None)  # type: ignore
        self.assertEqual(state.status, "failed")

    def test_step_budget_exhaustion_stops_safely(self) -> None:
        class InfiniteLoopProvider:
            def decide(self, state, tools):
                return {
                    "kind": "tool",
                    "current_objective": "Looping",
                    "hypothesis": "Looping",
                    "reasoning": "Looping",
                    "tool_call": ToolCall(name="get_revenue_metrics"),
                }

        repo = SimulatedCompanyRepository("payment_failure")
        controller = AgentController(
            ToolRegistry(repo), InfiniteLoopProvider(), max_steps=3,
        )
        state = controller.run("Investigate revenue.")
        self.assertEqual(state.status, "step_limit_reached")
        self.assertEqual(state.step_count, 3)

    def test_unregistered_tool_call_is_blocked_safely(self) -> None:
        repo = SimulatedCompanyRepository("payment_failure")
        registry = ToolRegistry(repo)
        result = registry.execute(ToolCall(name="non_existent_tool"))
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "unknown_tool")

    def test_invalid_action_propose_arguments_rejected_before_execution(self) -> None:
        repo = SimulatedCompanyRepository("inventory_supplier_failure")
        action_reg = ActionRegistry(repo, Decimal("50000"))
        res = action_reg.propose("create_purchase_request", {"invalid_arg": 123}, reason="r", evidence=[])
        self.assertFalse(res.ok)
        self.assertEqual(res.error.code, "invalid_input")


if __name__ == "__main__":
    unittest.main()
