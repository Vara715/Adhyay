"""Comprehensive PS5 End-to-End Integration & Synchronization Tests via FastAPI TestClient."""

from decimal import Decimal
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.api.runs import _RUNS
from backend.main import app
from backend.models.actions import VerificationOutcome


class PS5EndToEndIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        _RUNS.clear()

    def test_e2e_replacement_flow_via_api(self) -> None:
        """Full E2E replacement flow: Goal -> Case -> Investigate -> Action -> Verify -> RESOLVED."""
        response = self.client.post(
            "/api/runs",
            json={
                "goal": "Customer CUST-801 received defective laptop stand in order ORD-9002. Resolve the issue by replacement.",
                "scenario": "customer_damaged_replacement_available",
                "approval_threshold_inr": "50000",
                "step_delay_seconds": 0.0,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        run_id = data["run_id"]

        self.assertEqual(data["status"], "completed")
        self.assertIsNotNone(data.get("customer_case"))
        case = data["customer_case"]
        self.assertEqual(case["case_id"], "CASE-ORD-9002")
        self.assertEqual(case["customer_id"], "CUST-801")
        self.assertEqual(case["order_id"], "ORD-9002")
        self.assertEqual(case["status"], "RESOLVED")

        proposals = [p["action"] for p in data["action_proposals"]]
        self.assertIn("create_replacement", proposals)
        self.assertTrue(len(case["verification_results"]) > 0)
        self.assertIn("verified", case["verification_results"][0])

    def test_e2e_out_of_stock_adaptation_flow_via_api(self) -> None:
        """E2E adaptation flow: Replacement stockout -> Adapts to refund -> Verified -> RESOLVED."""
        response = self.client.post(
            "/api/runs",
            json={
                "goal": "Customer CUST-802 requested replacement for order ORD-9003.",
                "scenario": "customer_replacement_out_of_stock_adapts_refund",
                "approval_threshold_inr": "50000",
                "step_delay_seconds": 0.0,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["status"], "completed")
        self.assertIsNotNone(data.get("customer_case"))
        case = data["customer_case"]
        self.assertEqual(case["status"], "RESOLVED")

        proposals = [p["action"] for p in data["action_proposals"]]
        self.assertIn("issue_refund", proposals)

    def test_e2e_policy_restriction_escalation_flow_via_api(self) -> None:
        """E2E policy restriction flow: Shipped order cancellation -> Escalated safely -> ESCALATED."""
        response = self.client.post(
            "/api/runs",
            json={
                "goal": "Customer CUST-803 requested cancellation for shipped order ORD-9004.",
                "scenario": "customer_refund_denied_policy_escalation",
                "approval_threshold_inr": "50000",
                "step_delay_seconds": 0.0,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["status"], "completed")
        self.assertIsNotNone(data.get("customer_case"))
        case = data["customer_case"]
        self.assertEqual(case["status"], "ESCALATED")
        self.assertIsNotNone(case.get("escalation_reason"))
        self.assertIn("escalate_customer_case", [p["action"] for p in data["action_proposals"]])

    def test_e2e_high_value_approval_and_resume_flow_via_api(self) -> None:
        """E2E high-value approval flow: High-risk refund -> Pauses in AWAITING_APPROVAL -> Approve -> RESOLVED."""
        # 1. Start run with threshold 5000 (order ORD-9002 price is 6500 >= 5000)
        response = self.client.post(
            "/api/runs",
            json={
                "goal": "Customer CUST-801 requested refund for damaged order ORD-9002.",
                "scenario": "customer_damaged_replacement_available",
                "approval_threshold_inr": "5000",
                "step_delay_seconds": 0.0,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        run_id = data["run_id"]

        self.assertEqual(data["status"], "awaiting_approval")
        self.assertIsNotNone(data.get("customer_case"))
        self.assertEqual(data["customer_case"]["status"], "AWAITING_APPROVAL")

        # 2. Submit approval
        app_res = self.client.post(
            f"/api/runs/{run_id}/approval",
            json={"approved": True, "step_delay_seconds": 0.0},
        )
        self.assertEqual(app_res.status_code, 200)
        resumed_data = app_res.json()

        self.assertEqual(resumed_data["status"], "completed")
        self.assertEqual(resumed_data["customer_case"]["status"], "RESOLVED")
        self.assertIn("issue_refund", resumed_data["actions"][0])

    def test_e2e_anti_false_resolved_protection_via_api(self) -> None:
        """CRITICAL RULE TEST: Injected verification failure MUST return FAILED in API poll, NEVER RESOLVED."""
        from backend.tools.actions import ActionRegistry

        original_verify = ActionRegistry.verify

        def mock_failing_verify(self_reg, proposal, baseline):
            return VerificationOutcome(
                status="failed",
                detail="E2E simulated verification failure: State change rejected by system of record.",
                before=baseline,
                after={},
            )

        with patch.object(ActionRegistry, "verify", mock_failing_verify):
            response = self.client.post(
                "/api/runs",
                json={
                    "goal": "Customer CUST-801 received defective laptop stand in order ORD-9002. Resolve the issue by replacement.",
                    "scenario": "customer_damaged_replacement_available",
                    "approval_threshold_inr": "50000",
                    "step_delay_seconds": 0.0,
                },
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()

            # API response MUST NOT return RESOLVED!
            self.assertIsNotNone(data.get("customer_case"))
            case = data["customer_case"]
            self.assertNotEqual(case["status"], "RESOLVED")
            self.assertEqual(case["status"], "FAILED")
            self.assertTrue(len(case["unresolved_issues"]) > 0)


if __name__ == "__main__":
    unittest.main()
