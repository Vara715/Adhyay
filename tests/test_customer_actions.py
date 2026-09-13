"""Deterministic tests for PS5 Customer-Resolution Actions, Permissions, Approvals, State Mutations, and Verifications."""

from decimal import Decimal
import unittest

from backend.data.database import SimulatedCompanyRepository
from backend.data.scenarios import ActionFailurePlan, ScenarioDefinition, _base_data
from backend.tools.actions import ActionRegistry


class CustomerActionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = SimulatedCompanyRepository()
        self.registry = ActionRegistry(self.repo, approval_threshold_inr=Decimal("5000"))

    def test_all_actions_registered(self) -> None:
        names = self.registry.names
        self.assertEqual(len(names), 8)
        self.assertIn("issue_refund", names)
        self.assertIn("create_replacement", names)
        self.assertIn("cancel_order", names)
        self.assertIn("escalate_customer_case", names)

    def test_successful_refund_low_risk(self) -> None:
        # ORD-9001: price 2499.0 < 5000 threshold => low_risk
        args = {
            "order_id": "ORD-9001",
            "customer_id": "CUST-801",
            "amount_inr": "2499.00",
            "reason": "Defective static noise in left earpiece.",
        }
        proposal = self.registry.propose("issue_refund", args, reason="Defective product", evidence=["ORD-9001 defective"])
        self.assertEqual(proposal.permission_level, "low_risk")
        self.assertEqual(proposal.approval_status, "not_required")

        baseline = self.registry.capture_baseline(proposal)
        self.assertEqual(baseline["status"], "delivered")

        res = self.registry.execute(proposal)
        self.assertTrue(res.ok)
        self.assertEqual(proposal.approval_status, "executed")

        # Verify state mutation in database
        order = self.repo.get_order("ORD-9001")
        self.assertEqual(order["status"], "refunded")
        self.assertEqual(order["refund_state"], "completed")

        refunds = self.repo.get_collection("refunds")
        self.assertEqual(len(refunds), 1)
        self.assertEqual(refunds[0]["order_id"], "ORD-9001")

        # Run verification
        outcome = self.registry.verify(proposal, baseline)
        self.assertEqual(outcome.status, "verified")
        self.assertIn("verified", outcome.detail)

    def test_high_risk_refund_requires_approval_and_execution_succeeds_upon_approval(self) -> None:
        # ORD-9002: price 6500.0 >= 5000 threshold => high_risk
        args = {
            "order_id": "ORD-9002",
            "customer_id": "CUST-801",
            "amount_inr": "6500.00",
            "reason": "Damaged during transit.",
        }
        proposal = self.registry.propose("issue_refund", args, reason="Damaged high-value item", evidence=["ORD-9002 damaged"])
        self.assertEqual(proposal.permission_level, "high_risk")
        self.assertEqual(proposal.approval_status, "pending")

        # Execution without approval MUST fail
        exec_before = self.registry.execute(proposal)
        self.assertFalse(exec_before.ok)
        self.assertEqual(exec_before.error.code, "approval_required")

        # Approve action
        appr_res = self.registry.approve(proposal)
        self.assertTrue(appr_res.ok)
        self.assertEqual(proposal.approval_status, "approved")

        # Capture baseline and execute after approval
        baseline = self.registry.capture_baseline(proposal)
        exec_after = self.registry.execute(proposal)
        self.assertTrue(exec_after.ok)

        # Verify state mutation & post-action verification
        outcome = self.registry.verify(proposal, baseline)
        self.assertEqual(outcome.status, "verified")

    def test_successful_replacement_and_inventory_mutation(self) -> None:
        # Initial PR-100 inventory
        inv_before = next((i for i in self.repo.get_collection("inventory") if i["product_id"] == "PR-100"), {})
        stock_before = inv_before.get("on_hand", 0)

        args = {
            "order_id": "ORD-9001",
            "customer_id": "CUST-801",
            "product_id": "PR-100",
            "quantity": 1,
            "reason": "Defective item replacement.",
        }
        proposal = self.registry.propose("create_replacement", args, reason="Replacement dispatch", evidence=["ORD-9001 defective"])
        self.assertEqual(proposal.permission_level, "low_risk")

        baseline = self.registry.capture_baseline(proposal)
        res = self.registry.execute(proposal)
        self.assertTrue(res.ok)

        # State mutation check: inventory stock reduced by 1
        inv_after = next((i for i in self.repo.get_collection("inventory") if i["product_id"] == "PR-100"), {})
        self.assertEqual(inv_after.get("on_hand"), max(0, stock_before - 1))

        # Order replacement state updated
        order = self.repo.get_order("ORD-9001")
        self.assertEqual(order["replacement_state"], "completed")

        outcome = self.registry.verify(proposal, baseline)
        self.assertEqual(outcome.status, "verified")

    def test_successful_cancellation(self) -> None:
        args = {
            "order_id": "ORD-9005",
            "customer_id": "CUST-804",
            "reason": "Customer changed mind before fulfillment.",
        }
        proposal = self.registry.propose("cancel_order", args, reason="Pre-shipment cancellation", evidence=["ORD-9005 processing"])
        baseline = self.registry.capture_baseline(proposal)
        res = self.registry.execute(proposal)
        self.assertTrue(res.ok)

        order = self.repo.get_order("ORD-9005")
        self.assertEqual(order["status"], "cancelled")
        self.assertEqual(order["cancellation_state"], "completed")
        self.assertEqual(order["fulfillment_status"], "unfulfilled")

        outcome = self.registry.verify(proposal, baseline)
        self.assertEqual(outcome.status, "verified")

    def test_escalate_customer_case(self) -> None:
        args = {
            "case_id": "CS-10390",
            "customer_id": "CUST-803",
            "reason": "Post-dispatch cancellation policy block. Escalating to human agent.",
            "priority": "high",
        }
        proposal = self.registry.propose("escalate_customer_case", args, reason="Policy block escalation", evidence=["ORD-9004 shipped"])
        baseline = self.registry.capture_baseline(proposal)
        res = self.registry.execute(proposal)
        self.assertTrue(res.ok)

        tickets = self.repo.get_collection("support_tickets")
        cust_tickets = [t for t in tickets if t.get("category") == "customer_escalation" and t.get("customer_id") == "CUST-803"]
        self.assertEqual(len(cust_tickets), 1)
        self.assertEqual(cust_tickets[0]["severity"], "high")

        outcome = self.registry.verify(proposal, baseline)
        self.assertEqual(outcome.status, "verified")

    def test_action_rejection_flow(self) -> None:
        args = {
            "order_id": "ORD-9002",
            "customer_id": "CUST-801",
            "amount_inr": "6500.00",
            "reason": "Damaged item refund.",
        }
        proposal = self.registry.propose("issue_refund", args, reason="Refund request", evidence=["ORD-9002"])
        rej_res = self.registry.reject(proposal)
        self.assertTrue(rej_res.ok)
        self.assertEqual(proposal.approval_status, "rejected")

        # Executing rejected action must fail cleanly
        exec_res = self.registry.execute(proposal)
        self.assertFalse(exec_res.ok)
        self.assertEqual(exec_res.error.code, "invalid_action_state")

    def test_action_failure_plan_injection(self) -> None:
        # Scenario with injected action failure plan
        fail_scenario = ScenarioDefinition(
            key="test_action_fail",
            name="Test Action Fail",
            description="Test action failure plan",
            data=_base_data(),
            action_failure_plans=(ActionFailurePlan("issue_refund", "Simulated payment gateway timeout during refund."),),
        )
        self.repo._scenario = fail_scenario
        args = {
            "order_id": "ORD-9001",
            "customer_id": "CUST-801",
            "amount_inr": "2499.00",
            "reason": "Defective item.",
        }
        proposal = self.registry.propose("issue_refund", args, reason="Refund", evidence=[])
        exec_res = self.registry.execute(proposal)
        self.assertFalse(exec_res.ok)
        self.assertEqual(exec_res.error.code, "simulated_action_failed")
        self.assertEqual(proposal.approval_status, "failed")
        self.assertIn("Simulated payment gateway timeout", proposal.outcome_summary)


if __name__ == "__main__":
    unittest.main()
