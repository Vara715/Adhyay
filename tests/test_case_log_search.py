"""Tests for read-only scoped case log search tool."""

import unittest
from backend.data.database import SimulatedCompanyRepository
from backend.tools.logs import SearchCaseLogsInput, SearchCaseLogsTool


class SearchCaseLogsToolTests(unittest.TestCase):
    def test_log_search_filters_by_order_id(self) -> None:
        repo = SimulatedCompanyRepository("customer_wrong_product_received")
        tool = SearchCaseLogsTool()
        result = tool.execute(repo, SearchCaseLogsInput(order_id="ORD-9005"))
        self.assertTrue(result.ok)
        self.assertIn("logs", result.data)
        logs = result.data["logs"]
        self.assertTrue(len(logs) > 0)
        self.assertTrue(all(l.get("order_id") == "ORD-9005" for l in logs if "order_id" in l))

    def test_log_search_protects_against_secret_leakage(self) -> None:
        repo = SimulatedCompanyRepository("customer_wrong_product_received")
        tool = SearchCaseLogsTool()
        result = tool.execute(repo, SearchCaseLogsInput(order_id="ORD-9005"))
        for log_entry in result.data.get("logs", []):
            self.assertNotIn("api_key", log_entry)
            self.assertNotIn("secret", log_entry)
            self.assertNotIn("token", log_entry)


if __name__ == "__main__":
    unittest.main()
