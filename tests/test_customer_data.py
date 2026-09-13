"""Tests for PS5 Customer & Individual Order Data Layer."""

import unittest

from backend.data.database import SimulatedCompanyRepository
from backend.models.customer import Customer, CustomerOrder


class CustomerDataLayerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = SimulatedCompanyRepository()

    def test_customers_collection_is_populated(self) -> None:
        customers = self.repo.get_collection("customers")
        self.assertGreaterEqual(len(customers), 4)
        ids = [c["customer_id"] for c in customers]
        self.assertIn("CUST-801", ids)
        self.assertIn("CUST-802", ids)
        self.assertIn("CUST-803", ids)

    def test_get_customer_by_id(self) -> None:
        cust = self.repo.get_customer("CUST-801")
        self.assertIsNotNone(cust)
        self.assertEqual(cust["name"], "Aarav Sharma")
        self.assertEqual(cust["tier"], "VIP")
        self.assertIn("history_summary", cust)

        # Validate with Customer Pydantic model
        model = Customer.model_validate(cust)
        self.assertEqual(model.customer_id, "CUST-801")
        self.assertEqual(model.tier, "VIP")
        self.assertEqual(model.total_orders, 14)

    def test_customer_orders_collection_is_populated(self) -> None:
        orders = self.repo.get_collection("customer_orders")
        self.assertGreaterEqual(len(orders), 5)
        order_ids = [o["order_id"] for o in orders]
        self.assertIn("ORD-9001", order_ids)
        self.assertIn("ORD-9002", order_ids)
        self.assertIn("ORD-9003", order_ids)

    def test_get_customer_orders_returns_matching_orders(self) -> None:
        cust_orders = self.repo.get_customer_orders("CUST-801")
        self.assertEqual(len(cust_orders), 2)
        order_ids = [o["order_id"] for o in cust_orders]
        self.assertIn("ORD-9001", order_ids)
        self.assertIn("ORD-9002", order_ids)

    def test_get_order_returns_all_ps5_required_fields(self) -> None:
        ord_data = self.repo.get_order("ORD-9001")
        self.assertIsNotNone(ord_data)
        
        # Verify required PS5 order fields
        self.assertEqual(ord_data["order_id"], "ORD-9001")
        self.assertEqual(ord_data["customer_id"], "CUST-801")
        self.assertEqual(ord_data["product_id"], "PR-100")
        self.assertEqual(ord_data["order_date"], "2026-09-08")
        self.assertEqual(ord_data["price"], 2499.0)
        self.assertEqual(ord_data["status"], "delivered")
        self.assertEqual(ord_data["fulfillment_status"], "delivered")
        self.assertIn("issue_information", ord_data)
        self.assertIn("refund_state", ord_data)
        self.assertIn("replacement_state", ord_data)
        self.assertIn("cancellation_state", ord_data)

        # Validate with CustomerOrder Pydantic model
        model = CustomerOrder.model_validate(ord_data)
        self.assertEqual(model.order_id, "ORD-9001")
        self.assertEqual(model.refund_state, "eligible")
        self.assertEqual(model.replacement_state, "requested")

    def test_repository_deepcopy_isolation(self) -> None:
        cust1 = self.repo.get_customer("CUST-801")
        cust1["name"] = "Mutated Name"
        
        cust_fresh = self.repo.get_customer("CUST-801")
        self.assertEqual(cust_fresh["name"], "Aarav Sharma")


if __name__ == "__main__":
    unittest.main()
