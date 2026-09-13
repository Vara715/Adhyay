"""Deterministic read-only customer investigation and resolution policy tools for PS5."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.data.database import SimulatedCompanyRepository
from backend.models.tools import ToolResult
from backend.tools.base import ReadOnlyTool


# Input Schemas
class GetCustomerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: str | None = Field(default=None, description="Customer ID (e.g. CUST-801)")
    email: str | None = Field(default=None, description="Customer email address")


class GetOrderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str = Field(min_length=1, description="Order ID (e.g. ORD-9001)")


class GetCustomerOrdersInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: str = Field(min_length=1, description="Customer ID (e.g. CUST-801)")
    status: str | None = Field(default=None, description="Optional order status filter")


class GetProductDetailsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str | None = Field(default=None, description="Product ID (e.g. PR-100)")
    category: str | None = Field(default=None, description="Product category filter")


class GetPolicyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_type: Literal["refund", "replacement", "cancellation", "all"] = Field(
        default="all", description="Policy category to inspect"
    )


class CheckEligibilityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str = Field(min_length=1, description="Order ID to evaluate")
    resolution_type: Literal["refund", "replacement", "cancellation"] = Field(
        description="Type of resolution requested"
    )


class GetCustomerInventoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str = Field(min_length=1, description="Product ID to check stock for")


# Tool Implementations
class GetCustomerTool(ReadOnlyTool[GetCustomerInput]):
    name = "get_customer"
    description = "Retrieve customer profile, tier, contact details, and past interaction history."
    input_model = GetCustomerInput

    def execute(self, repository: SimulatedCompanyRepository, arguments: GetCustomerInput) -> ToolResult:
        customers = repository.get_collection("customers")
        if arguments.customer_id:
            matched = [c for c in customers if c.get("customer_id") == arguments.customer_id]
        elif arguments.email:
            matched = [c for c in customers if c.get("email") == arguments.email]
        else:
            matched = customers

        if not matched:
            return ToolResult.failure(
                self.name, "not_found", "No customer profile found matching the query criteria."
            )

        return ToolResult.success(
            self.name,
            f"Retrieved profile for customer {matched[0]['customer_id']} ({matched[0]['name']}).",
            {"customer": matched[0] if (arguments.customer_id or arguments.email) else matched},
        )


class GetOrderTool(ReadOnlyTool[GetOrderInput]):
    name = "get_order"
    description = "Retrieve detailed information for a specific customer order including fulfillment, issue details, and resolution state."
    input_model = GetOrderInput

    def execute(self, repository: SimulatedCompanyRepository, arguments: GetOrderInput) -> ToolResult:
        order = repository.get_order(arguments.order_id)
        if not order:
            return ToolResult.failure(
                self.name, "not_found", f"No customer order found with order_id '{arguments.order_id}'."
            )
        return ToolResult.success(
            self.name,
            f"Retrieved order {order['order_id']} for customer {order['customer_id']} (Status: {order['status']}).",
            {"order": order},
        )


class GetCustomerOrdersTool(ReadOnlyTool[GetCustomerOrdersInput]):
    name = "get_customer_orders"
    description = "List all orders placed by a specific customer, optionally filtered by order status."
    input_model = GetCustomerOrdersInput

    def execute(self, repository: SimulatedCompanyRepository, arguments: GetCustomerOrdersInput) -> ToolResult:
        orders = repository.get_customer_orders(arguments.customer_id)
        if arguments.status:
            orders = [o for o in orders if o.get("status") == arguments.status]

        if not orders:
            return ToolResult.failure(
                self.name, "not_found", f"No orders found for customer '{arguments.customer_id}'."
            )

        return ToolResult.success(
            self.name,
            f"Found {len(orders)} order(s) for customer {arguments.customer_id}.",
            {"customer_id": arguments.customer_id, "orders": orders, "count": len(orders)},
        )


class GetProductDetailsTool(ReadOnlyTool[GetProductDetailsInput]):
    name = "get_product_details"
    description = "Retrieve product catalog information, unit price, category, and sales history."
    input_model = GetProductDetailsInput

    def execute(self, repository: SimulatedCompanyRepository, arguments: GetProductDetailsInput) -> ToolResult:
        products = repository.get_collection("products")
        if arguments.product_id:
            products = [p for p in products if p.get("product_id") == arguments.product_id]
        if arguments.category:
            products = [p for p in products if p.get("category") == arguments.category]

        if not products:
            return ToolResult.failure(self.name, "not_found", "No products match the specified criteria.")

        return ToolResult.success(
            self.name,
            f"Retrieved catalog details for {len(products)} product(s).",
            {"products": products},
        )


class GetPolicyTool(ReadOnlyTool[GetPolicyInput]):
    name = "get_policy"
    description = "Retrieve deterministic local company resolution policies for refunds, replacements, cancellations, and approval rules."
    input_model = GetPolicyInput

    def execute(self, repository: SimulatedCompanyRepository, arguments: GetPolicyInput) -> ToolResult:
        policies = {
            "refund_policy": {
                "max_auto_refund_inr": 5000.0,
                "return_window_days": 14,
                "allowed_reasons": ["defective", "damaged_in_transit", "incorrect_item", "billing_error"],
                "approval_rule": "Refunds valued >= ₹5,000 require human reviewer approval.",
                "vip_fast_track": True,
            },
            "replacement_policy": {
                "requires_in_stock": True,
                "replacement_window_days": 30,
                "allowed_reasons": ["defective", "damaged_in_transit", "wrong_size"],
                "out_of_stock_fallback": "If replacement item is out of stock, offer full refund or escalation.",
            },
            "cancellation_policy": {
                "auto_cancellation_allowed_statuses": ["processing", "pending"],
                "disallowed_statuses": ["shipped", "delivered"],
                "post_dispatch_rule": "Orders already shipped cannot be auto-cancelled. Agent must escalate to human support.",
            },
        }

        ptype = arguments.policy_type
        selected = policies if ptype == "all" else {f"{ptype}_policy": policies.get(f"{ptype}_policy")}

        return ToolResult.success(
            self.name,
            f"Retrieved {ptype} resolution policy guidelines.",
            {"policies": selected},
        )


class CheckResolutionEligibilityTool(ReadOnlyTool[CheckEligibilityInput]):
    name = "check_customer_resolution_eligibility"
    description = "Evaluate deterministic policy eligibility, constraint blocks, and approval requirements for an order resolution."
    input_model = CheckEligibilityInput

    def execute(self, repository: SimulatedCompanyRepository, arguments: CheckEligibilityInput) -> ToolResult:
        order = repository.get_order(arguments.order_id)
        if not order:
            return ToolResult.failure(self.name, "not_found", f"Order '{arguments.order_id}' not found.")

        cust = repository.get_customer(order["customer_id"])
        product_id = order.get("product_id")
        price = order.get("price", 0.0)

        resolution = arguments.resolution_type
        eligible = False
        requires_approval = False
        blocked_by = None
        recommendation = ""
        reason = ""

        if resolution == "refund":
            if order.get("refund_state") == "completed":
                reason = "Order has already been refunded."
            else:
                eligible = True
                requires_approval = price >= 5000.0
                reason = (
                    f"Order is eligible for refund. Amount: ₹{price}."
                    + (" Requires human approval (>= ₹5,000)." if requires_approval else " Within auto-approval limit.")
                )
                recommendation = "Execute issue_customer_refund action."

        elif resolution == "replacement":
            inv_list = repository.get_collection("inventory")
            inv_record = next((i for i in inv_list if i.get("product_id") == product_id), {})
            on_hand = inv_record.get("on_hand", 0) - inv_record.get("reserved", 0)

            if on_hand <= 0 or order.get("replacement_state") == "blocked_out_of_stock":
                eligible = False
                blocked_by = "out_of_stock"
                reason = f"Replacement product '{product_id}' is out of stock (available: {on_hand})."
                recommendation = "Adapt resolution: Offer full refund or escalate to human agent."
            else:
                eligible = True
                reason = f"Replacement product '{product_id}' is in stock (available: {on_hand})."
                recommendation = "Execute process_order_replacement action."

        elif resolution == "cancellation":
            status = order.get("status")
            if status in ["shipped", "delivered"] or order.get("cancellation_state") == "blocked_shipped":
                eligible = False
                blocked_by = "already_shipped"
                reason = f"Order status is '{status}'. Cancellation post-dispatch is forbidden by policy."
                recommendation = "Escalate to human agent for manual logistics handling."
            else:
                eligible = True
                reason = f"Order status is '{status}'. Eligible for immediate cancellation."
                recommendation = "Execute cancel_customer_order action."

        return ToolResult.success(
            self.name,
            f"Evaluated {resolution} eligibility for order {arguments.order_id}: eligible={eligible}.",
            {
                "order_id": arguments.order_id,
                "resolution_type": resolution,
                "eligible": eligible,
                "requires_human_approval": requires_approval,
                "blocked_by": blocked_by,
                "reason": reason,
                "recommendation": recommendation,
                "customer_tier": cust.get("tier") if cust else "Standard",
                "order_price_inr": price,
            },
        )


class GetCustomerInventoryTool(ReadOnlyTool[GetCustomerInventoryInput]):
    name = "get_customer_inventory"
    description = "Check real-time customer-facing stock availability for replacement verification."
    input_model = GetCustomerInventoryInput

    def execute(self, repository: SimulatedCompanyRepository, arguments: GetCustomerInventoryInput) -> ToolResult:
        inventory = repository.get_collection("inventory")
        record = next((item for item in inventory if item.get("product_id") == arguments.product_id), None)
        if not record:
            return ToolResult.failure(
                self.name, "not_found", f"No inventory record for product_id '{arguments.product_id}'."
            )

        available = record.get("on_hand", 0) - record.get("reserved", 0)
        return ToolResult.success(
            self.name,
            f"Product {arguments.product_id} stock: {available} units available.",
            {
                "product_id": arguments.product_id,
                "on_hand": record.get("on_hand"),
                "reserved": record.get("reserved"),
                "available_for_replacement": max(0, available),
                "in_stock": available > 0,
            },
        )
