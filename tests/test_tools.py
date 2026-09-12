"""Deterministic tests for the Stage 2 simulation and read-only tools."""

import unittest

from backend.data.database import SimulatedCompanyRepository
from backend.data.seed import available_scenarios
from backend.tools.registry import ToolRegistry


class ToolRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = SimulatedCompanyRepository("inventory_supplier_failure")
        self.tools = ToolRegistry(self.repository)

    def test_all_required_tools_are_registered(self) -> None:
        self.assertEqual(set(self.tools.names), {
            "get_revenue_metrics", "get_order_metrics", "get_product_sales",
            "get_inventory_status", "get_supplier_status", "get_payment_status",
            "get_service_health", "get_recent_deployments", "get_system_logs",
        })

    def test_seed_data_is_reproducible(self) -> None:
        first = ToolRegistry(SimulatedCompanyRepository("payment_failure")).run("get_payment_status")
        second = ToolRegistry(SimulatedCompanyRepository("payment_failure")).run("get_payment_status")
        self.assertEqual(first.data, second.data)
        self.assertEqual(first.data["failure_rate_percent"], 42.0)

    def test_scenario_failure_is_structured_and_deterministic(self) -> None:
        first = self.tools.run("get_inventory_status")
        second = self.tools.run("get_inventory_status")
        self.assertFalse(first.ok)
        self.assertEqual(first.error.code, "simulated_service_unavailable")
        self.assertTrue(first.error.retryable)
        self.assertTrue(second.ok)

    def test_inputs_are_validated(self) -> None:
        result = self.tools.run("get_recent_deployments", {"limit": 99})
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "invalid_input")

    def test_discovery_metadata_contains_concise_schema(self) -> None:
        metadata = {item.name: item for item in self.tools.discover()}
        self.assertEqual(len(metadata), 9)
        self.assertIn("properties", metadata["get_system_logs"].input_schema)
        self.assertLessEqual(len(metadata["get_system_logs"].description), 100)

    def test_malformed_tool_call_is_blocked_before_execution(self) -> None:
        result = self.tools.execute({"name": "get_payment_status", "arguments": ["not-an-object"]})
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "malformed_tool_call")

    def test_invalid_tool_call_arguments_do_not_reach_tool(self) -> None:
        result = self.tools.execute({"name": "get_recent_deployments", "arguments": {"limit": 99}})
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "invalid_input")

    def test_unknown_tool_call_is_blocked(self) -> None:
        result = self.tools.execute({"name": "delete_everything", "arguments": {}})
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "unknown_tool")

    def test_unknown_lookup_returns_structured_failure(self) -> None:
        result = self.tools.run("get_product_sales", {"product_id": "PR-404"})
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "not_found")

    def test_four_scenarios_are_available(self) -> None:
        self.assertEqual(len(available_scenarios()), 4)


if __name__ == "__main__":
    unittest.main()
