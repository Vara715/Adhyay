"""Deterministic tests for Stage 7 post-action verification.

Covers both levels, matching the Stage 6 test split:
  * ActionRegistry-direct tests, which prove the underlying state actually changes and that
    ``verify()`` correctly judges verified / failed / inconclusive outcomes.
  * AgentController integration tests, which prove the loop always runs verification after a
    real execution, never after a rejection, and always surfaces a non-"verified" outcome in
    the final report rather than silently claiming success.
"""

import unittest
from decimal import Decimal

from backend.agent.controller import AgentController
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
            confidence="high",
        )


class ActionRegistryVerificationTests(unittest.TestCase):
    """Exercises ActionRegistry.capture_baseline/execute/verify directly."""

    @staticmethod
    def _registry(scenario: str, threshold: str = "50000") -> tuple[SimulatedCompanyRepository, ActionRegistry]:
        repository = SimulatedCompanyRepository(scenario)
        return repository, ActionRegistry(repository, Decimal(threshold))

    def test_support_ticket_verifies_successfully_after_a_real_state_change(self) -> None:
        repository, registry = self._registry("inventory_supplier_failure")
        proposal = registry.propose(
            "create_support_ticket",
            {"title": "Investigate revenue drop", "summary": "Root cause under investigation.", "severity": "high"},
            reason="Escalate for visibility.", evidence=["Revenue is down 25.8% versus last period."],
        )
        baseline = registry.capture_baseline(proposal)
        result = registry.execute(proposal)
        self.assertTrue(result.ok)

        outcome = registry.verify(proposal, baseline)

        self.assertEqual(outcome.status, "verified")
        self.assertEqual(baseline["open_ticket_count"], 1)  # one open ticket exists in the seed data
        self.assertEqual(outcome.after["status"], "open")
        tickets = repository.get_collection("support_tickets")
        self.assertTrue(any(t.get("category") == "agent_escalation" for t in tickets))

    def test_purchase_request_verification_is_inconclusive_pending_fulfillment(self) -> None:
        repository, registry = self._registry("inventory_supplier_failure")
        proposal = registry.propose(
            "create_purchase_request",
            {"supplier_id": "SUP-01", "product_id": "PR-100", "quantity": 20, "unit_cost_inr": "500"},
            reason="Restock a nearly out-of-stock product.", evidence=["PR-100 on-hand is 2 units."],
        )
        baseline = registry.capture_baseline(proposal)
        result = registry.execute(proposal)
        self.assertTrue(result.ok)

        outcome = registry.verify(proposal, baseline)

        self.assertEqual(outcome.status, "inconclusive")
        self.assertEqual(baseline["on_hand"], 2)
        requests = repository.get_collection("purchase_requests")
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]["status"], "submitted")

    def test_rollback_verifies_successfully_when_the_deployment_and_service_are_confirmed(self) -> None:
        repository, registry = self._registry("inventory_supplier_failure")
        proposal = registry.propose(
            "rollback_deployment", {"deployment_id": "DEP-501", "reason": "Confirm rollback mechanics."},
            reason="Test rollback of a real deployment.", evidence=[],
        )
        registry.approve(proposal)
        baseline = registry.capture_baseline(proposal)
        result = registry.execute(proposal)
        self.assertTrue(result.ok)

        outcome = registry.verify(proposal, baseline)

        self.assertEqual(outcome.status, "verified")
        deployments = repository.get_collection("deployments")
        rolled_back = next(item for item in deployments if item["deployment_id"] == "DEP-501")
        self.assertEqual(rolled_back["status"], "rolled_back")

    def test_rollback_verification_fails_when_the_deployment_cannot_be_confirmed(self) -> None:
        """Execution reports success (no failure plan matches), but nothing was actually rolled
        back — this is exactly the case verification exists to catch."""
        repository, registry = self._registry("inventory_supplier_failure")
        proposal = registry.propose(
            "rollback_deployment", {"deployment_id": "DEP-000-DOES-NOT-EXIST", "reason": "Bad id."},
            reason="Simulate an agent targeting the wrong deployment.", evidence=[],
        )
        registry.approve(proposal)
        baseline = registry.capture_baseline(proposal)
        result = registry.execute(proposal)
        self.assertTrue(result.ok)  # execution layer has no reason to fail this call

        outcome = registry.verify(proposal, baseline)

        self.assertEqual(outcome.status, "failed")
        self.assertIn("could not be confirmed", outcome.detail)


class AgentControllerVerificationTests(unittest.TestCase):
    """Exercises the full controller-enforced execute → verify flow."""

    @staticmethod
    def _controller(scenario: str, provider, threshold: str = "50000", **options):
        repository = SimulatedCompanyRepository(scenario)
        tool_registry = ToolRegistry(repository)
        action_registry = ActionRegistry(repository, Decimal(threshold))
        controller = AgentController(tool_registry, provider, action_registry=action_registry, **options)
        return controller, repository

    def test_low_risk_action_is_verified_and_final_report_has_no_unresolved_issues(self) -> None:
        provider = _OnceThenFinishProvider(
            "create_support_ticket",
            {"title": "Investigate revenue drop", "summary": "Root cause under investigation.", "severity": "high"},
        )
        controller, _ = self._controller("inventory_supplier_failure", provider)

        state = controller.run("Revenue dropped; investigate.")

        self.assertEqual(state.status, "completed")
        event_types = [event.event_type for event in state.events]
        self.assertIn("verification", event_types)
        verification_event = next(e for e in state.events if e.event_type == "verification")
        self.assertIn("verified", verification_event.summary)
        self.assertEqual(state.verification_notes, [])
        self.assertEqual(state.final_result.unresolved_issues, [])

    def test_low_risk_action_with_inconclusive_verification_surfaces_as_unresolved(self) -> None:
        provider = _OnceThenFinishProvider(
            "create_purchase_request",
            {"supplier_id": "SUP-01", "product_id": "PR-100", "quantity": 20, "unit_cost_inr": "500"},
        )
        controller, _ = self._controller("inventory_supplier_failure", provider)

        state = controller.run("Revenue dropped; investigate.")

        self.assertEqual(state.status, "completed")
        verification_event = next(e for e in state.events if e.event_type == "verification")
        self.assertIn("inconclusive", verification_event.summary)
        self.assertEqual(len(state.verification_notes), 1)
        # The structured report must reflect the unresolved verification even though the
        # decision provider itself declared "high" confidence.
        self.assertEqual(state.final_result.unresolved_issues, state.verification_notes)

    def test_approved_high_risk_action_is_verified_after_resume(self) -> None:
        provider = _OnceThenFinishProvider(
            "rollback_deployment", {"deployment_id": "DEP-501", "reason": "Confirm rollback mechanics."},
        )
        controller, repository = self._controller("inventory_supplier_failure", provider)
        state = controller.run("Revenue dropped; investigate.")
        self.assertEqual(state.status, "awaiting_approval")

        resumed = controller.resume_after_approval(state, approved=True)

        self.assertEqual(resumed.status, "completed")
        verification_event = next(e for e in resumed.events if e.event_type == "verification")
        self.assertIn("verified", verification_event.summary)
        self.assertEqual(resumed.final_result.unresolved_issues, [])
        deployments = repository.get_collection("deployments")
        self.assertEqual(next(d for d in deployments if d["deployment_id"] == "DEP-501")["status"], "rolled_back")

    def test_approved_high_risk_action_with_failed_verification_is_never_reported_as_success(self) -> None:
        provider = _OnceThenFinishProvider(
            "rollback_deployment", {"deployment_id": "DEP-000-DOES-NOT-EXIST", "reason": "Bad id."},
        )
        controller, _ = self._controller("inventory_supplier_failure", provider)
        state = controller.run("Revenue dropped; investigate.")
        self.assertEqual(state.status, "awaiting_approval")

        resumed = controller.resume_after_approval(state, approved=True)

        self.assertEqual(resumed.status, "completed")
        verification_event = next(e for e in resumed.events if e.event_type == "verification")
        self.assertIn("failed", verification_event.summary)
        self.assertEqual(len(resumed.verification_notes), 1)
        self.assertIn("could not be confirmed", resumed.final_result.unresolved_issues[0])

    def test_rejected_action_never_triggers_verification(self) -> None:
        provider = _OnceThenFinishProvider(
            "rollback_deployment", {"deployment_id": "DEP-501", "reason": "Confirm rollback mechanics."},
        )
        controller, repository = self._controller("inventory_supplier_failure", provider)
        state = controller.run("Revenue dropped; investigate.")

        resumed = controller.resume_after_approval(state, approved=False)

        self.assertEqual(resumed.status, "completed")
        event_types = [event.event_type for event in resumed.events]
        self.assertNotIn("verification", event_types)
        self.assertEqual(resumed.verification_notes, [])
        deployments = repository.get_collection("deployments")
        self.assertEqual(next(d for d in deployments if d["deployment_id"] == "DEP-501")["status"], "successful")

    def test_build_decision_request_includes_verification_notes_and_proposals(self) -> None:
        from backend.agent.prompts import build_decision_request
        from backend.models.agent import AgentState
        from backend.models.actions import ActionProposal
        state = AgentState(original_goal="Investigate anomaly")
        state.verification_notes.append("rollback_deployment: Service health is still degraded.")
        state.action_proposals.append(ActionProposal(
            action="rollback_deployment", arguments={"deployment_id": "DEP-502"},
            reason="Test rollback", evidence=[], estimated_impact={}, risk="High",
            permission_level="high_risk", approval_status="approved",
        ))
        req = build_decision_request(state, [])
        user_content = req.messages[1].content
        self.assertIn("Verification notes:", user_content)
        self.assertIn("Service health is still degraded", user_content)
        self.assertIn("Proposed actions:", user_content)

    def test_llm_decision_provider_maps_action_tool_calls(self) -> None:
        from backend.agent.decisions import LLMDecisionProvider
        from backend.models.agent import AgentState
        from backend.models.llm import LLMResponse
        from backend.models.tools import ToolCall
        class FakeClient:
            def complete(self, req):
                return LLMResponse(content="Proposing rollback", tool_call=ToolCall(name="rollback_deployment", arguments={"deployment_id": "DEP-502"}))
        provider = LLMDecisionProvider(FakeClient())
        decision = provider.decide(AgentState(original_goal="Investigate anomaly"), [])
        self.assertEqual(decision.kind, "action")
        self.assertEqual(decision.action_call.name, "rollback_deployment")



if __name__ == "__main__":
    unittest.main()

