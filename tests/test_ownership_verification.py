"""Tests for customer-order ownership verification security checks."""

import unittest
from backend.data.database import SimulatedCompanyRepository
from backend.tools.customer import CheckEligibilityInput, CheckResolutionEligibilityTool, GetOrderInput, GetOrderTool


class OwnershipVerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = SimulatedCompanyRepository()

    def test_valid_ownership_succeeds(self) -> None:
        tool = GetOrderTool()
        result = tool.execute(self.repo, GetOrderInput(order_id="ORD-9001", customer_id="CUST-801"))
        self.assertTrue(result.ok)
        self.assertEqual(result.data["order"]["customer_id"], "CUST-801")

    def test_invalid_ownership_returns_security_mismatch_error(self) -> None:
        tool = GetOrderTool()
        # ORD-9004 belongs to CUST-803, not CUST-801
        result = tool.execute(self.repo, GetOrderInput(order_id="ORD-9004", customer_id="CUST-801"))
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "ownership_mismatch")
        self.assertIn("Access Denied", result.error.message)

    def test_eligibility_check_blocks_on_ownership_mismatch(self) -> None:
        tool = CheckResolutionEligibilityTool()
        result = tool.execute(
            self.repo,
            CheckEligibilityInput(order_id="ORD-9004", customer_id="CUST-801", resolution_type="refund"),
        )
        self.assertTrue(result.ok)
        self.assertFalse(result.data["eligible"])
        self.assertEqual(result.data["blocked_by"], "ownership_mismatch")
        self.assertIn("Security Violation", result.data["reason"])


if __name__ == "__main__":
    unittest.main()
