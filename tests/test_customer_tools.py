"""Unit tests for PS5 Read-Only Customer Investigation Tools & Registry Integration."""

import unittest

from backend.data.database import SimulatedCompanyRepository
from backend.data.scenarios import FailurePlan, ScenarioDefinition, _base_data
from backend.tools.registry import ToolRegistry


class CustomerToolsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = SimulatedCompanyRepository()
        self.registry = ToolRegistry(self.repo)

    def test_tool_registry_includes_all_customer_tools(self) -> None:
        names = self.registry.names
        self.assertEqual(len(names), 18)
        expected_customer_tools = [
            "get_customer",
            "get_order",
            "get_customer_orders",
            "get_product_details",
            "get_policy",
            "check_customer_resolution_eligibility",
            "get_customer_inventory",
        ]
        for tool_name in expected_customer_tools:
            self.assertIn(tool_name, names)

    def test_get_customer_by_id_and_email(self) -> None:
        res1 = self.registry.run("get_customer", {"customer_id": "CUST-801"})
        self.assertTrue(res1.ok)
        self.assertEqual(res1.data["customer"]["name"], "Aarav Sharma")
        self.assertEqual(res1.data["customer"]["tier"], "VIP")

        res2 = self.registry.run("get_customer", {"email": "priya.patel@example.com"})
        self.assertTrue(res2.ok)
        self.assertEqual(res2.data["customer"]["customer_id"], "CUST-802")

        res3 = self.registry.run("get_customer", {"customer_id": "NON-EXISTENT"})
        self.assertFalse(res3.ok)
        self.assertEqual(res3.error.code, "not_found")

    def test_get_order_details(self) -> None:
        res = self.registry.run("get_order", {"order_id": "ORD-9001"})
        self.assertTrue(res.ok)
        order = res.data["order"]
        self.assertEqual(order["customer_id"], "CUST-801")
        self.assertEqual(order["price"], 2499.0)
        self.assertEqual(order["refund_state"], "eligible")

        missing = self.registry.run("get_order", {"order_id": "ORD-9999"})
        self.assertFalse(missing.ok)
        self.assertEqual(missing.error.code, "not_found")

    def test_get_customer_orders(self) -> None:
        res = self.registry.run("get_customer_orders", {"customer_id": "CUST-801"})
        self.assertTrue(res.ok)
        self.assertEqual(len(res.data["orders"]), 2)

        res_filtered = self.registry.run("get_customer_orders", {"customer_id": "CUST-801", "status": "delivered"})
        self.assertTrue(res_filtered.ok)
        self.assertEqual(len(res_filtered.data["orders"]), 2)

    def test_get_product_details(self) -> None:
        res = self.registry.run("get_product_details", {"product_id": "PR-100"})
        self.assertTrue(res.ok)
        self.assertEqual(res.data["products"][0]["name"], "Nimbus Wireless Headphones")

    def test_get_policy(self) -> None:
        res_all = self.registry.run("get_policy", {"policy_type": "all"})
        self.assertTrue(res_all.ok)
        self.assertIn("refund_policy", res_all.data["policies"])
        self.assertIn("replacement_policy", res_all.data["policies"])
        self.assertIn("cancellation_policy", res_all.data["policies"])
        self.assertEqual(res_all.data["policies"]["refund_policy"]["max_auto_refund_inr"], 5000.0)

        res_refund = self.registry.run("get_policy", {"policy_type": "refund"})
        self.assertTrue(res_refund.ok)
        self.assertIn("refund_policy", res_refund.data["policies"])

    def test_check_customer_resolution_eligibility_refund(self) -> None:
        # ORD-9001: price 2499 (< 5000), eligible
        res1 = self.registry.run("check_customer_resolution_eligibility", {"order_id": "ORD-9001", "resolution_type": "refund"})
        self.assertTrue(res1.ok)
        self.assertTrue(res1.data["eligible"])
        self.assertFalse(res1.data["requires_human_approval"])

        # ORD-9002: price 6500 (>= 5000), eligible but requires approval
        res2 = self.registry.run("check_customer_resolution_eligibility", {"order_id": "ORD-9002", "resolution_type": "refund"})
        self.assertTrue(res2.ok)
        self.assertTrue(res2.data["eligible"])
        self.assertTrue(res2.data["requires_human_approval"])

    def test_check_customer_resolution_eligibility_replacement_out_of_stock(self) -> None:
        # ORD-9003: product PR-300, replacement requested but out of stock
        res = self.registry.run("check_customer_resolution_eligibility", {"order_id": "ORD-9003", "resolution_type": "replacement"})
        self.assertTrue(res.ok)
        self.assertFalse(res.data["eligible"])
        self.assertEqual(res.data["blocked_by"], "out_of_stock")
        self.assertIn("Adapt resolution", res.data["recommendation"])

    def test_check_customer_resolution_eligibility_cancellation_shipped(self) -> None:
        # ORD-9004: status is shipped, cancellation post-dispatch blocked
        res = self.registry.run("check_customer_resolution_eligibility", {"order_id": "ORD-9004", "resolution_type": "cancellation"})
        self.assertTrue(res.ok)
        self.assertFalse(res.data["eligible"])
        self.assertEqual(res.data["blocked_by"], "already_shipped")
        self.assertIn("Escalate to human agent", res.data["recommendation"])

    def test_get_customer_inventory(self) -> None:
        # PR-200 has available stock (in_stock = True)
        res_in_stock = self.registry.run("get_customer_inventory", {"product_id": "PR-200"})
        self.assertTrue(res_in_stock.ok)
        self.assertTrue(res_in_stock.data["in_stock"])
        self.assertGreater(res_in_stock.data["available_for_replacement"], 0)

        # PR-100 in default scenario inventory_supplier_failure is out of available stock (available = 0)
        res_out_of_stock = self.registry.run("get_customer_inventory", {"product_id": "PR-100"})
        self.assertTrue(res_out_of_stock.ok)
        self.assertFalse(res_out_of_stock.data["in_stock"])
        self.assertEqual(res_out_of_stock.data["available_for_replacement"], 0)


    def test_failure_injection_on_customer_tools(self) -> None:
        # Create custom scenario definition with failure plan on get_customer
        fail_scenario = ScenarioDefinition(
            key="test_fail",
            name="Test Fail",
            description="Test failure injection",
            data=_base_data(),
            failure_plans=(FailurePlan("get_customer", 1, "Customer service database timeout."),),
        )
        self.repo._scenario = fail_scenario
        res = self.registry.run("get_customer", {"customer_id": "CUST-801"})
        self.assertFalse(res.ok)
        self.assertEqual(res.error.code, "simulated_service_unavailable")
        self.assertTrue(res.error.retryable)


if __name__ == "__main__":
    unittest.main()
