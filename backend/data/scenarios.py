"""Small, deterministic operational scenarios for the local simulator."""

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FailurePlan:
    """A deterministic temporary failure: no randomness or external calls."""

    tool_name: str
    fails_for_calls: int
    message: str


@dataclass(frozen=True)
class DataCondition:
    """A deterministic non-fatal quality issue surfaced with a tool result."""

    tool_name: str
    code: str
    message: str


@dataclass(frozen=True)
class ActionFailurePlan:
    """A future action failure kept as scenario data until actions are implemented."""

    action_name: str
    message: str


@dataclass(frozen=True)
class ScenarioDefinition:
    key: str
    name: str
    description: str
    data: dict[str, Any]
    failure_plans: tuple[FailurePlan, ...] = field(default_factory=tuple)
    data_conditions: tuple[DataCondition, ...] = field(default_factory=tuple)
    action_failure_plans: tuple[ActionFailurePlan, ...] = field(default_factory=tuple)


def _base_data() -> dict[str, Any]:
    return {
        "sales": {
            "currency": "INR",
            "period": "today",
            "current_revenue": 118_000,
            "previous_revenue": 120_000,
            "change_percent": -1.7,
        },
        "orders": {
            "period": "today",
            "current_orders": 118,
            "previous_orders": 120,
            "average_order_value": 1_000,
            "cancellation_rate_percent": 2.5,
            "conversion_rate_percent": 4.8,
        },
        "products": [
            {
                "product_id": "PR-100",
                "name": "Nimbus Wireless Headphones",
                "category": "Electronics",
                "unit_price": 2_499,
                "units_sold_current": 38,
                "units_sold_previous": 40,
                "revenue_current": 94_962,
                "revenue_change_percent": -5.0,
            },
            {
                "product_id": "PR-200",
                "name": "Atlas Laptop Stand",
                "category": "Accessories",
                "unit_price": 1_499,
                "units_sold_current": 16,
                "units_sold_previous": 15,
                "revenue_current": 23_984,
                "revenue_change_percent": 6.7,
            },
            {
                "product_id": "PR-300",
                "name": "Orbit USB-C Hub",
                "category": "Accessories",
                "unit_price": 1_299,
                "units_sold_current": 12,
                "units_sold_previous": 13,
                "revenue_current": 15_588,
                "revenue_change_percent": -7.7,
            },
        ],
        "inventory": [
            {
                "product_id": "PR-100",
                "on_hand": 110,
                "reorder_point": 25,
                "reserved": 4,
                "supplier_id": "SUP-01",
                "last_restocked": "2026-09-07",
            },
            {
                "product_id": "PR-200",
                "on_hand": 48,
                "reorder_point": 20,
                "reserved": 3,
                "supplier_id": "SUP-02",
                "last_restocked": "2026-09-08",
            },
            {
                "product_id": "PR-300",
                "on_hand": 64,
                "reorder_point": 25,
                "reserved": 1,
                "supplier_id": "SUP-01",
                "last_restocked": "2026-09-05",
            },
        ],
        "suppliers": [
            {
                "supplier_id": "SUP-01",
                "name": "Nimbus Components Pvt Ltd",
                "status": "operational",
                "active_shipment": "SH-1201",
                "expected_arrival": "2026-09-12",
                "delay_days": 0,
            },
            {
                "supplier_id": "SUP-02",
                "name": "Atlas Works Ltd",
                "status": "operational",
                "active_shipment": "SH-1202",
                "expected_arrival": "2026-09-11",
                "delay_days": 0,
            },
        ],
        "payments": {
            "period": "today",
            "attempted_transactions": 120,
            "successful_transactions": 117,
            "failed_transactions": 3,
            "failure_rate_percent": 2.5,
            "average_latency_ms": 420,
            "top_failure_reason": "insufficient_funds",
        },
        "support_tickets": [
            {
                "ticket_id": "T-1001",
                "created_at": "2026-09-10T09:10:00Z",
                "category": "delivery",
                "status": "open",
                "summary": "Customer asked about standard delivery time.",
            },
            {
                "ticket_id": "T-1002",
                "created_at": "2026-09-10T10:05:00Z",
                "category": "product",
                "status": "closed",
                "summary": "Product compatibility question resolved.",
            },
        ],
        "service_health": {
            "overall_status": "healthy",
            "checkout": {"status": "healthy", "error_rate_percent": 0.4, "latency_ms": 280},
            "catalog": {"status": "healthy", "error_rate_percent": 0.1, "latency_ms": 120},
            "payment_gateway": {"status": "healthy", "error_rate_percent": 0.8, "latency_ms": 420},
        },
        "deployments": [
            {
                "deployment_id": "DEP-501",
                "service": "catalog",
                "version": "2.4.1",
                "deployed_at": "2026-09-08T07:30:00Z",
                "status": "successful",
                "summary": "Catalog search ranking adjustment.",
            }
        ],
        "purchase_requests": [],
        "logs": [
            {
                "timestamp": "2026-09-10T10:00:00Z",
                "service": "checkout",
                "level": "INFO",
                "message": "Checkout completed successfully.",
            },
            {
                "timestamp": "2026-09-10T10:02:00Z",
                "service": "payment_gateway",
                "level": "INFO",
                "message": "Payment authorization completed in 410ms.",
            },
        ],
    }


def _inventory_supplier_failure() -> ScenarioDefinition:
    data = _base_data()
    data["sales"].update(current_revenue=89_000, previous_revenue=120_000, change_percent=-25.8)
    data["orders"].update(current_orders=81, previous_orders=120, average_order_value=1_099, cancellation_rate_percent=3.1)
    data["products"][0].update(units_sold_current=6, units_sold_previous=42, revenue_current=14_994, revenue_change_percent=-85.7)
    data["inventory"][0].update(on_hand=2, reserved=2, last_restocked="2026-08-21")
    data["suppliers"][0].update(status="delayed", expected_arrival="2026-09-17", delay_days=5)
    data["logs"].append({"timestamp": "2026-09-10T08:10:00Z", "service": "inventory", "level": "WARNING", "message": "PR-100 stock is below reorder point; supplier shipment SH-1201 delayed."})
    return ScenarioDefinition(
        key="inventory_supplier_failure",
        name="Inventory and supplier failure",
        description="A best-selling item is nearly out of stock because its inbound supplier shipment is delayed.",
        data=data,
        failure_plans=(FailurePlan("get_inventory_status", 1, "Inventory service is temporarily unavailable. Retry or use another source."),),
    )


def _payment_failure() -> ScenarioDefinition:
    data = _base_data()
    data["sales"].update(current_revenue=92_000, previous_revenue=120_000, change_percent=-23.3)
    data["orders"].update(current_orders=82, previous_orders=120, average_order_value=1_122, cancellation_rate_percent=4.8, conversion_rate_percent=3.3)
    data["payments"].update(attempted_transactions=143, successful_transactions=83, failed_transactions=60, failure_rate_percent=42.0, average_latency_ms=2_800, top_failure_reason="gateway_timeout")
    data["service_health"]["payment_gateway"].update(status="degraded", error_rate_percent=41.5, latency_ms=2_800)
    data["service_health"]["overall_status"] = "degraded"
    data["logs"].append({"timestamp": "2026-09-10T09:15:00Z", "service": "payment_gateway", "level": "ERROR", "message": "Gateway timeout rate exceeded alert threshold."})
    return ScenarioDefinition(
        "payment_failure", "Payment failure", "A payment gateway timeout surge causes checkout payment failures.", data,
        data_conditions=(DataCondition(
            "get_payment_status", "incomplete_data",
            "Payment failure-reason breakdown is delayed; aggregate totals remain available.",
        ),),
    )


def _deployment_service_failure() -> ScenarioDefinition:
    data = _base_data()
    data["sales"].update(current_revenue=87_000, previous_revenue=120_000, change_percent=-27.5)
    data["orders"].update(current_orders=76, previous_orders=120, average_order_value=1_145, cancellation_rate_percent=7.2, conversion_rate_percent=2.9)
    data["service_health"].update(overall_status="degraded")
    data["service_health"]["checkout"].update(status="degraded", error_rate_percent=18.7, latency_ms=2_100)
    data["deployments"].insert(0, {"deployment_id": "DEP-502", "service": "checkout", "version": "3.8.0", "deployed_at": "2026-09-10T07:45:00Z", "status": "successful", "summary": "Checkout tax-calculation refactor."})
    data["logs"].append({"timestamp": "2026-09-10T08:02:00Z", "service": "checkout", "level": "ERROR", "message": "Tax calculation null reference after DEP-502; checkout request rejected."})
    return ScenarioDefinition(
        "deployment_service_failure", "Deployment and service failure", "A checkout deployment introduces elevated errors shortly after release.", data,
        data_conditions=(DataCondition(
            "get_recent_deployments", "contradictory_evidence",
            "The deployment is marked successful; runtime logs are required to confirm its operational impact.",
        ),),
        action_failure_plans=(ActionFailurePlan(
            "rollback_deployment", "Simulated rollback failed because the target artifact is unavailable.",
        ),),
    )


def _misleading_initial_hypothesis() -> ScenarioDefinition:
    data = _base_data()
    data["sales"].update(current_revenue=96_000, previous_revenue=120_000, change_percent=-20.0)
    data["orders"].update(current_orders=91, previous_orders=120, average_order_value=1_055, cancellation_rate_percent=6.8, conversion_rate_percent=3.7)
    data["inventory"][1].update(on_hand=21, reorder_point=20)
    data["payments"].update(failure_rate_percent=2.8, failed_transactions=3, successful_transactions=105)
    data["support_tickets"] = [
        {"ticket_id": "T-2001", "created_at": "2026-09-10T08:30:00Z", "category": "checkout", "status": "open", "summary": "Delivery fee doubled at checkout for customers outside metro areas."},
        {"ticket_id": "T-2002", "created_at": "2026-09-10T09:02:00Z", "category": "checkout", "status": "open", "summary": "Customer abandoned cart after unexpected shipping charge."},
    ]
    data["deployments"].insert(0, {"deployment_id": "DEP-503", "service": "pricing", "version": "1.6.2", "deployed_at": "2026-09-10T07:20:00Z", "status": "successful", "summary": "Shipping-zone pricing configuration update."})
    data["logs"].append({"timestamp": "2026-09-10T07:25:00Z", "service": "pricing", "level": "WARNING", "message": "Fallback shipping zone selected for 38% of checkout addresses."})
    return ScenarioDefinition(
        "misleading_initial_hypothesis", "Misleading initial hypothesis", "Borderline stock initially looks suspicious, but support and pricing evidence point to shipping-fee configuration.", data,
        data_conditions=(DataCondition(
            "get_recent_deployments", "stale_data",
            "Deployment feed is delayed; corroborate this information with current system logs.",
        ),),
    )


SCENARIOS: dict[str, ScenarioDefinition] = {
    scenario.key: scenario
    for scenario in (
        _inventory_supplier_failure(),
        _payment_failure(),
        _deployment_service_failure(),
        _misleading_initial_hypothesis(),
    )
}


def get_scenario_definition(key: str) -> ScenarioDefinition:
    """Return an immutable scenario definition or raise a useful lookup error."""
    try:
        return SCENARIOS[key]
    except KeyError as error:
        available = ", ".join(sorted(SCENARIOS))
        raise ValueError(f"Unknown scenario '{key}'. Available scenarios: {available}.") from error


def copy_scenario_data(key: str) -> dict[str, Any]:
    """Return fresh scenario state so callers cannot mutate seed data."""
    return deepcopy(get_scenario_definition(key).data)
