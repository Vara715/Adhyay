"""A resettable data-access layer over local, deterministic seed data."""

from copy import deepcopy
from typing import Any

from backend.data.scenarios import get_scenario_definition
from backend.data.seed import DEFAULT_SCENARIO, load_seed_data
from backend.models.tools import ToolError, ToolWarning


class SimulatedCompanyRepository:
    """Local scenario state and deterministic failure injection for read-only tools."""

    def __init__(self, scenario_key: str = DEFAULT_SCENARIO) -> None:
        self.load_scenario(scenario_key)

    def load_scenario(self, scenario_key: str) -> None:
        self._scenario = get_scenario_definition(scenario_key)
        self._data = load_seed_data(scenario_key)
        self._tool_call_counts: dict[str, int] = {}
        self._actions_executed: list[dict[str, Any]] = []

    @property
    def scenario_key(self) -> str:
        return self._scenario.key

    def get_collection(self, name: str) -> Any:
        """Return a copy to make tool reads side-effect free."""
        return deepcopy(self._data[name])

    def get_customer(self, customer_id: str) -> dict[str, Any] | None:
        """Retrieve a specific customer profile by ID."""
        customers = self.get_collection("customers")
        return next((c for c in customers if c.get("customer_id") == customer_id), None)

    def get_customer_orders(self, customer_id: str) -> list[dict[str, Any]]:
        """Retrieve all orders placed by a specific customer."""
        orders = self.get_collection("customer_orders")
        return [o for o in orders if o.get("customer_id") == customer_id]

    def get_order(self, order_id: str) -> dict[str, Any] | None:
        """Retrieve a specific customer order by order ID."""
        orders = self.get_collection("customer_orders")
        return next((o for o in orders if o.get("order_id") == order_id), None)


    def check_failure(self, tool_name: str) -> ToolError | None:
        """Consume a scenario-defined failure window for this tool call."""
        calls = self._tool_call_counts.get(tool_name, 0) + 1
        self._tool_call_counts[tool_name] = calls
        for plan in self._scenario.failure_plans:
            if plan.tool_name == tool_name and calls <= plan.fails_for_calls:
                return ToolError(code="simulated_service_unavailable", message=plan.message, retryable=True)
        return None

    def get_warnings(self, tool_name: str) -> list[ToolWarning]:
        """Return scenario-defined data-quality warnings without changing tool data."""
        return [
            ToolWarning(code=condition.code, message=condition.message)
            for condition in self._scenario.data_conditions
            if condition.tool_name == tool_name
        ]

    def get_action_failure(self, action_name: str) -> ToolError | None:
        """Expose deterministic future-action failure metadata without executing an action."""
        for plan in self._scenario.action_failure_plans:
            if plan.action_name == action_name:
                return ToolError(code="simulated_action_failed", message=plan.message, retryable=False)
        return None

    def record_action(self, action_record: dict[str, Any]) -> None:
        """Persist a successfully executed simulated action for audit/verification."""
        self._actions_executed.append(action_record)

    def list_recorded_actions(self) -> list[dict[str, Any]]:
        """Return a defensive copy of every action executed against this scenario."""
        return deepcopy(self._actions_executed)

    def apply_action_effect(self, action_name: str, arguments: dict[str, Any], action_id: str) -> None:
        """Mutate the simulated environment to reflect one successfully executed action.

        This is what makes verification meaningful: without a real (if simplified) state
        change, there would be nothing for a later read to confirm or contradict.
        """
        if action_name == "create_purchase_request":
            self._data.setdefault("purchase_requests", []).append({
                "request_id": action_id,
                "supplier_id": arguments.get("supplier_id"),
                "product_id": arguments.get("product_id"),
                "quantity": arguments.get("quantity"),
                "unit_cost_inr": arguments.get("unit_cost_inr"),
                "status": "submitted",
            })
        elif action_name == "create_support_ticket":
            self._data.setdefault("support_tickets", []).append({
                "ticket_id": action_id,
                "category": "agent_escalation",
                "status": "open",
                "title": arguments.get("title"),
                "summary": arguments.get("summary"),
                "severity": arguments.get("severity"),
            })
        elif action_name == "rollback_deployment":
            deployment_id = arguments.get("deployment_id")
            deployment = next(
                (item for item in self._data.get("deployments", []) if item.get("deployment_id") == deployment_id),
                None,
            )
            if deployment is None:
                return
            deployment["status"] = "rolled_back"
            service = deployment.get("service")
            service_health = self._data.get("service_health", {})
            if service and service in service_health:
                service_health[service]["status"] = "healthy"
                service_health[service]["error_rate_percent"] = 0.5
                still_degraded = any(
                    isinstance(entry, dict) and entry.get("status") != "healthy"
                    for key, entry in service_health.items()
                    if key != "overall_status"
                )
                service_health["overall_status"] = "degraded" if still_degraded else "healthy"
        elif action_name == "issue_refund":
            order_id = arguments.get("order_id")
            orders = self._data.get("customer_orders", [])
            order = next((o for o in orders if o.get("order_id") == order_id), None)
            if order:
                order["status"] = "refunded"
                order["refund_state"] = "completed"
            self._data.setdefault("refunds", []).append({
                "refund_id": action_id,
                "order_id": order_id,
                "customer_id": arguments.get("customer_id"),
                "amount_inr": float(arguments.get("amount_inr", 0)),
                "reason": arguments.get("reason"),
                "status": "completed",
            })
        elif action_name == "create_replacement":
            order_id = arguments.get("order_id")
            product_id = arguments.get("product_id")
            qty = int(arguments.get("quantity", 1))
            orders = self._data.get("customer_orders", [])
            order = next((o for o in orders if o.get("order_id") == order_id), None)
            if order:
                order["replacement_state"] = "completed"
            inventory = self._data.get("inventory", [])
            inv_item = next((i for i in inventory if i.get("product_id") == product_id), None)
            if inv_item:
                inv_item["on_hand"] = max(0, inv_item.get("on_hand", 0) - qty)
            self._data.setdefault("replacements", []).append({
                "replacement_id": action_id,
                "order_id": order_id,
                "customer_id": arguments.get("customer_id"),
                "product_id": product_id,
                "quantity": qty,
                "status": "dispatched",
            })
        elif action_name == "cancel_order":
            order_id = arguments.get("order_id")
            orders = self._data.get("customer_orders", [])
            order = next((o for o in orders if o.get("order_id") == order_id), None)
            if order:
                order["status"] = "cancelled"
                order["cancellation_state"] = "completed"
                order["fulfillment_status"] = "unfulfilled"
        elif action_name == "escalate_customer_case":
            self._data.setdefault("support_tickets", []).append({
                "ticket_id": action_id,
                "customer_id": arguments.get("customer_id"),
                "case_id": arguments.get("case_id"),
                "category": "customer_escalation",
                "status": "open",
                "title": f"Escalation for Customer {arguments.get('customer_id')}",
                "summary": arguments.get("reason"),
                "severity": arguments.get("priority", "medium"),
            })

