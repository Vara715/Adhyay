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
                "sku": "SKU-NIMBUS-100",
                "name": "Nimbus Wireless Headphones",
                "brand": "Nimbus",
                "model": "P1-Pro",
                "category": "Electronics",
                "unit_price": 2_499,
                "units_sold_current": 38,
                "units_sold_previous": 40,
                "revenue_current": 94_962,
                "revenue_change_percent": -5.0,
                "specifications": "Bluetooth 5.2, Active Noise Cancellation, 30hr battery",
            },
            {
                "product_id": "PR-200",
                "sku": "SKU-ATLAS-200",
                "name": "Atlas Laptop Stand",
                "brand": "Atlas",
                "model": "P2-Stand",
                "category": "Accessories",
                "unit_price": 1_499,
                "units_sold_current": 16,
                "units_sold_previous": 15,
                "revenue_current": 23_984,
                "revenue_change_percent": 6.7,
                "specifications": "Aluminum Alloy, Ergonomic Adjustable Height, 15-inch max",
            },
            {
                "product_id": "PR-300",
                "sku": "SKU-ORBIT-300",
                "name": "Orbit USB-C Hub",
                "brand": "Orbit",
                "model": "P3-Hub",
                "category": "Accessories",
                "unit_price": 1_299,
                "units_sold_current": 12,
                "units_sold_previous": 13,
                "revenue_current": 15_588,
                "revenue_change_percent": -7.7,
                "specifications": "7-in-1 Multiport Adapter, 100W PD Pass-through, HDMI 4K",
            },
        ],
        "shipments": [
            {
                "shipment_id": "SH-9001",
                "order_id": "ORD-9001",
                "tracking_number": "TRK-88101",
                "carrier": "ExpressLogistics",
                "status": "delivered",
                "dispatch_date": "2026-09-08",
                "delivery_date": "2026-09-10",
            },
            {
                "shipment_id": "SH-9002",
                "order_id": "ORD-9002",
                "tracking_number": "TRK-88102",
                "carrier": "ExpressLogistics",
                "status": "delivered",
                "dispatch_date": "2026-09-09",
                "delivery_date": "2026-09-11",
            },
            {
                "shipment_id": "SH-9004",
                "order_id": "ORD-9004",
                "tracking_number": "TRK-88104",
                "carrier": "ExpressLogistics",
                "status": "in_transit",
                "dispatch_date": "2026-09-07",
                "delivery_date": "2026-09-12",
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
        "customers": [
            {
                "customer_id": "CUST-801",
                "name": "Aarav Sharma",
                "email": "aarav.sharma@example.com",
                "tier": "VIP",
                "history_summary": "High-value loyal customer (14 past orders). 0 previous returns.",
                "total_orders": 14,
                "total_spent_inr": 48_500.0,
                "notes": "Fast-track support eligible.",
            },
            {
                "customer_id": "CUST-802",
                "name": "Priya Patel",
                "email": "priya.patel@example.com",
                "tier": "Standard",
                "history_summary": "Standard customer (3 past orders). 1 previous replacement.",
                "total_orders": 3,
                "total_spent_inr": 5_497.0,
                "notes": "Prefers email communication.",
            },
            {
                "customer_id": "CUST-803",
                "name": "Vikram Malhotra",
                "email": "vikram.m@example.com",
                "tier": "Gold",
                "history_summary": "Frequent buyer (8 past orders). Active subscription.",
                "total_orders": 8,
                "total_spent_inr": 22_100.0,
                "notes": "Verified business account.",
            },
            {
                "customer_id": "CUST-804",
                "name": "Ananya Roy",
                "email": "ananya.roy@example.com",
                "tier": "Standard",
                "history_summary": "First-time buyer (1 past order).",
                "total_orders": 1,
                "total_spent_inr": 1_299.0,
                "notes": "New account.",
            },
        ],
        "customer_orders": [
            {
                "order_id": "ORD-9001",
                "customer_id": "CUST-801",
                "product_id": "PR-100",
                "order_date": "2026-09-08",
                "price": 2_499.0,
                "status": "delivered",
                "fulfillment_status": "delivered",
                "issue_information": "Defective product received: Left earpiece produces static noise.",
                "refund_state": "eligible",
                "replacement_state": "requested",
                "cancellation_state": "none",
            },
            {
                "order_id": "ORD-9002",
                "customer_id": "CUST-801",
                "product_id": "PR-200",
                "order_date": "2026-09-09",
                "price": 6_500.0,
                "status": "delivered",
                "fulfillment_status": "delivered",
                "issue_information": "Package arrived damaged during transit. High-value item.",
                "refund_state": "requested",
                "replacement_state": "eligible",
                "cancellation_state": "none",
            },
            {
                "order_id": "ORD-9003",
                "customer_id": "CUST-802",
                "product_id": "PR-300",
                "order_date": "2026-09-09",
                "price": 1_299.0,
                "status": "processing",
                "fulfillment_status": "pending",
                "issue_information": "Customer requested order replacement, but product PR-300 stock is out.",
                "refund_state": "eligible",
                "replacement_state": "blocked_out_of_stock",
                "cancellation_state": "eligible",
            },
            {
                "order_id": "ORD-9004",
                "customer_id": "CUST-803",
                "product_id": "PR-100",
                "order_date": "2026-09-07",
                "price": 2_499.0,
                "status": "shipped",
                "fulfillment_status": "in_transit",
                "issue_information": "Late cancellation requested after order dispatched from warehouse.",
                "refund_state": "none",
                "replacement_state": "none",
                "cancellation_state": "blocked_shipped",
            },
            {
                "order_id": "ORD-9005",
                "customer_id": "CUST-804",
                "product_id": "PR-300",
                "order_date": "2026-09-10",
                "price": 1_299.0,
                "status": "processing",
                "fulfillment_status": "pending",
                "issue_information": "None",
                "refund_state": "none",
                "replacement_state": "none",
                "cancellation_state": "requested",
            },
        ],
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
        "case_logs": [
            {
                "timestamp": "2026-09-10T09:30:00Z",
                "order_id": "ORD-9005",
                "customer_id": "CUST-804",
                "log_type": "warehouse_packing",
                "message": "Warehouse barcode scan matched item: Phone 2 (P2-X) packed into box for Order ORD-9005. Mismatch detected with order manifest Phone 1.",
            },
            {
                "timestamp": "2026-09-10T11:15:00Z",
                "order_id": "ORD-9005",
                "customer_id": "CUST-804",
                "log_type": "shipping_scan",
                "message": "Courier dispatch scan: Package tracking TRK-88102 departed warehouse hub.",
            },
            {
                "timestamp": "2026-09-09T14:20:00Z",
                "order_id": "ORD-9002",
                "customer_id": "CUST-801",
                "log_type": "warehouse_packing",
                "message": "Warehouse barcode scan matched item: Atlas Laptop Stand (PR-200) packed for Order ORD-9002.",
            },
            {
                "timestamp": "2026-09-09T16:05:00Z",
                "order_id": "ORD-9002",
                "customer_id": "CUST-801",
                "log_type": "shipping_scan",
                "message": "Express courier note: Outer container suffered severe box crush during transit.",
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


def _customer_damaged_replacement_available() -> ScenarioDefinition:
    data = _base_data()
    return ScenarioDefinition(
        key="customer_damaged_replacement_available",
        name="Customer damaged product replacement available",
        description="Customer received a damaged product and requests a replacement. Replacement inventory is in stock.",
        data=data,
    )


def _customer_replacement_out_of_stock_adapts_refund() -> ScenarioDefinition:
    data = _base_data()
    data["inventory"][2].update(on_hand=0, reserved=0)
    data["customer_orders"][2].update(replacement_state="blocked_out_of_stock")
    return ScenarioDefinition(
        key="customer_replacement_out_of_stock_adapts_refund",
        name="Customer replacement stockout adapts to refund",
        description="Customer requested a replacement unit, but inventory is out of stock. The agent dynamically adapts to issue a refund.",
        data=data,
    )


def _customer_refund_denied_policy_escalation() -> ScenarioDefinition:
    data = _base_data()
    return ScenarioDefinition(
        key="customer_refund_denied_policy_escalation",
        name="Customer post-dispatch cancellation policy escalation",
        description="Customer requested cancellation for an order that has already shipped. Policy forbids auto-cancellation post-dispatch, requiring agent escalation.",
        data=data,
    )


def _customer_investigation_tool_failure_adapts() -> ScenarioDefinition:
    data = _base_data()
    return ScenarioDefinition(
        key="customer_investigation_tool_failure_adapts",
        name="Customer investigation tool failure adaptation",
        description="A customer resolution lookup tool experiences a temporary failure. The agent detects the failure and adapts cleanly.",
        data=data,
        failure_plans=(
            FailurePlan(
                "get_customer_inventory",
                1,
                "Customer inventory service is temporarily unavailable. Retry or check catalog details.",
            ),
        ),
    )


def _customer_wrong_product_received() -> ScenarioDefinition:
    data = _base_data()
    return ScenarioDefinition(
        key="customer_wrong_product_received",
        name="Customer wrong product received (Multimodal Supported)",
        description="Customer ordered Phone 1 but received Phone 2. Attachment image and warehouse packing logs confirm mismatch. Claim status: SUPPORTED.",
        data=data,
    )


def _customer_inconclusive_image_log_lookup() -> ScenarioDefinition:
    data = _base_data()
    return ScenarioDefinition(
        key="customer_inconclusive_image_log_lookup",
        name="Customer unreadable image evidence (Inconclusive)",
        description="Customer uploaded a blurry image. Attachment extraction marks EVIDENCE_INCONCLUSIVE. Agent investigates logs without inventing details.",
        data=data,
    )


def _customer_wrong_product_stockout_adapts() -> ScenarioDefinition:
    data = _base_data()
    data["inventory"][0].update(on_hand=0, reserved=0)
    return ScenarioDefinition(
        key="customer_wrong_product_stockout_adapts",
        name="Wrong product received with replacement stockout",
        description="Customer claim is SUPPORTED, but replacement stock is unavailable. The agent dynamically adapts to issue a refund.",
        data=data,
    )


def _customer_claim_contradicted() -> ScenarioDefinition:
    data = _base_data()
    return ScenarioDefinition(
        key="customer_claim_contradicted",
        name="Customer claim contradicted by photo and log evidence",
        description="Customer claims wrong item, but uploaded image and factory packing scans confirm correct item. Claim status: CONTRADICTED.",
        data=data,
    )


def _customer_ownership_mismatch_escalates() -> ScenarioDefinition:
    data = _base_data()
    return ScenarioDefinition(
        key="customer_ownership_mismatch_escalates",
        name="Customer order ownership mismatch (Security Escalation)",
        description="Customer CUST-801 attempts to query or claim resolution for order ORD-9004 belonging to CUST-803. System detects security mismatch and escalates safely.",
        data=data,
    )


SCENARIOS: dict[str, ScenarioDefinition] = {
    scenario.key: scenario
    for scenario in (
        _inventory_supplier_failure(),
        _payment_failure(),
        _deployment_service_failure(),
        _misleading_initial_hypothesis(),
        _customer_damaged_replacement_available(),
        _customer_replacement_out_of_stock_adapts_refund(),
        _customer_refund_denied_policy_escalation(),
        _customer_investigation_tool_failure_adapts(),
        _customer_wrong_product_received(),
        _customer_inconclusive_image_log_lookup(),
        _customer_wrong_product_stockout_adapts(),
        _customer_claim_contradicted(),
        _customer_ownership_mismatch_escalates(),
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
