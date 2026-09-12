"""Deterministic tests for Stage 6 action tools, permissions, and human approval."""

import unittest
from decimal import Decimal

from backend.agent.controller import AgentController
from backend.agent.decisions import EvidenceBasedDecisionProvider
from backend.data.database import SimulatedCompanyRepository
from backend.models.actions import ActionCall
from backend.models.agent import AgentDecision
from backend.tools.actions import ActionRegistry
from backend.tools.registry import ToolRegistry


class _OnceThenFinishProvider:
    """Test double: proposes one action, then finishes regardless of the outcome."""

    def __init__(self, action_name: str, arguments: dict) -> None:
        self._action_name = action_name
        self._arguments = arguments
        self._offered = False

    def decide(self, state, tools):
        if not self._offered:
            self._offered = True
            return AgentDecision(
                kind="action",
                current_objective="Attempt remediation for the identified root cause.",
                hypothesis=state.current_hypothesis,
                reasoning="Test-only remediation attempt.",
                action_call=ActionCall(name=self._action_name, arguments=self._arguments),
            )
        return AgentDecision(
            kind="finish",
            current_objective="Conclude after the remediation attempt.",
            hypothesis=state.current_hypothesis,
            reasoning="Test-only completion.",
            conclusion="Investigation concluded after the remediation attempt.",
            confidence="medium",
        )


class ActionRegistryPermissionTests(unittest.TestCase):
    """Exercises ActionRegistry directly: permission computation, validation, never-bypass."""

    @staticmethod
    def _registry(scenario: str, threshold: str = "50000") -> tuple[SimulatedCompanyRepository, ActionRegistry]:
        repository = SimulatedCompanyRepository(scenario)
        return repository, ActionRegistry(repository, Decimal(threshold))

    def test_low_value_purchase_is_low_risk_and_high_value_is_high_risk(self) -> None:
        _, registry = self._registry("inventory_supplier_failure")
        low = registry.propose(
            "create_purchase_request",
            {"supplier_id": "SUP-01", "product_id": "PR-100", "quantity": 10, "unit_cost_inr": "500"},
            reason="Restock a low-availability product.", evidence=["PR-100 is nearly out of stock."],
        )
        high = registry.propose(
            "create_purchase_request",
            {"supplier_id": "SUP-01", "product_id": "PR-100", "quantity": 1000, "unit_cost_inr": "500"},
            reason="Large restock order.", evidence=["PR-100 is nearly out of stock."],
        )
        self.assertEqual(low.permission_level, "low_risk")
        self.assertEqual(low.approval_status, "not_required")
        self.assertEqual(high.permission_level, "high_risk")
        self.assertEqual(high.approval_status, "pending")

    def test_rollback_is_always_high_risk_regardless_of_threshold(self) -> None:
        _, registry = self._registry("deployment_service_failure", threshold="1")
        proposal = registry.propose(
            "rollback_deployment", {"deployment_id": "DEP-502", "reason": "Errors began right after this release."},
            reason="Checkout errors began right after this deployment.", evidence=["Checkout error rate is elevated."],
        )
        self.assertEqual(proposal.permission_level, "high_risk")

    def test_high_risk_action_can_never_bypass_approval(self) -> None:
        _, registry = self._registry("deployment_service_failure")
        proposal = registry.propose(
            "rollback_deployment", {"deployment_id": "DEP-502", "reason": "Attempted bypass."},
            reason="Attempt to execute without approval.", evidence=[],
        )
        result = registry.execute(proposal)
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "approval_required")

    def test_invalid_arguments_are_rejected_before_any_execution_attempt(self) -> None:
        _, registry = self._registry("inventory_supplier_failure")
        result = registry.propose("create_purchase_request", {"supplier_id": "SUP-01"}, reason="Incomplete request.", evidence=[])
        self.assertFalse(result.ok)

    def test_unknown_action_name_is_rejected(self) -> None:
        _, registry = self._registry("inventory_supplier_failure")
        result = registry.propose("delete_database", {}, reason="Not a registered action.", evidence=[])
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "unknown_tool")


class AgentControllerActionTests(unittest.TestCase):
    """Exercises the full controller-enforced propose → gate → execute/approve → verify-ready flow."""

    @staticmethod
    def _controller(scenario: str, provider, threshold: str = "50000", **options):
        repository = SimulatedCompanyRepository(scenario)
        tool_registry = ToolRegistry(repository)
        action_registry = ActionRegistry(repository, Decimal(threshold))
        controller = AgentController(tool_registry, provider, action_registry=action_registry, **options)
        return controller, repository

    def test_low_risk_action_executes_automatically_and_is_recorded(self) -> None:
        provider = _OnceThenFinishProvider(
            "create_support_ticket",
            {"title": "Investigate revenue drop", "summary": "Root cause under investigation.", "severity": "high"},
        )
        controller, repository = self._controller("inventory_supplier_failure", provider)
        state = controller.run("Revenue dropped; investigate.")

        event_types = [event.event_type for event in state.events]
        self.assertEqual(state.status, "completed")
        self.assertIn("action_proposed", event_types)
        self.assertIn("action_executed", event_types)
        self.assertNotIn("approval_required", event_types)
        self.assertEqual(len(repository.list_recorded_actions()), 1)
        self.assertTrue(any("create_support_ticket" in entry for entry in state.final_result.actions_executed))

    def test_high_risk_action_halts_for_approval_and_never_executes_without_it(self) -> None:
        provider = _OnceThenFinishProvider(
            "rollback_deployment", {"deployment_id": "DEP-502", "reason": "Errors began right after this release."},
        )
        controller, repository = self._controller("deployment_service_failure", provider)
        state = controller.run("Revenue dropped; investigate.")

        self.assertEqual(state.status, "awaiting_approval")
        self.assertIsNotNone(state.pending_action)
        self.assertEqual(state.pending_action.approval_status, "pending")
        self.assertEqual(repository.list_recorded_actions(), [])
        event_types = [event.event_type for event in state.events]
        self.assertIn("approval_required", event_types)
        self.assertNotIn("action_executed", event_types)

    def test_approved_high_risk_action_executes_and_investigation_continues(self) -> None:
        provider = _OnceThenFinishProvider(
            "rollback_deployment", {"deployment_id": "DEP-999", "reason": "Test rollback with no injected failure."},
        )
        controller, repository = self._controller("inventory_supplier_failure", provider)
        state = controller.run("Revenue dropped; investigate.")
        self.assertEqual(state.status, "awaiting_approval")

        resumed = controller.resume_after_approval(state, approved=True)

        self.assertEqual(resumed.status, "completed")
        self.assertEqual(len(repository.list_recorded_actions()), 1)
        self.assertIsNone(resumed.pending_action)
        self.assertIn("action_executed", [event.event_type for event in resumed.events])

    def test_rejected_high_risk_action_does_not_execute_and_investigation_continues_safely(self) -> None:
        provider = _OnceThenFinishProvider(
            "rollback_deployment", {"deployment_id": "DEP-502", "reason": "Errors began right after this release."},
        )
        controller, repository = self._controller("deployment_service_failure", provider)
        state = controller.run("Revenue dropped; investigate.")

        resumed = controller.resume_after_approval(state, approved=False)

        self.assertEqual(resumed.status, "completed")
        self.assertEqual(repository.list_recorded_actions(), [])
        self.assertIsNone(resumed.pending_action)
        self.assertIn("adaptation", [event.event_type for event in resumed.events])
        self.assertTrue(any("rejected" in entry for entry in resumed.actions))

    def test_action_failure_after_approval_is_reported_not_hidden(self) -> None:
        provider = _OnceThenFinishProvider(
            "rollback_deployment", {"deployment_id": "DEP-502", "reason": "Errors began right after this release."},
        )
        controller, repository = self._controller("deployment_service_failure", provider)
        state = controller.run("Revenue dropped; investigate.")

        resumed = controller.resume_after_approval(state, approved=True)

        self.assertEqual(resumed.status, "completed")
        self.assertTrue(any("Simulated rollback failed" in failure for failure in resumed.failures))
        self.assertEqual(repository.list_recorded_actions(), [])

    def test_resume_without_a_pending_action_raises(self) -> None:
        controller, _ = self._controller("inventory_supplier_failure", EvidenceBasedDecisionProvider())
        state = controller.run("Revenue dropped significantly today. Investigate why.")
        self.assertEqual(state.status, "completed")
        with self.assertRaises(ValueError):
            controller.resume_after_approval(state, approved=True)

    def test_action_decision_without_a_configured_action_registry_fails_safely(self) -> None:
        provider = _OnceThenFinishProvider("create_support_ticket", {"title": "t", "summary": "s"})
        controller = AgentController(
            ToolRegistry(SimulatedCompanyRepository("inventory_supplier_failure")), provider,
        )
        state = controller.run("Investigate revenue.")
        self.assertEqual(state.status, "failed")


if __name__ == "__main__":
    unittest.main()
