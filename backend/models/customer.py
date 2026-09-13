"""Pydantic models for customer and individual customer order data."""

from pydantic import BaseModel, ConfigDict, Field


class Customer(BaseModel):
    """Customer record for customer resolution agent investigations."""

    model_config = ConfigDict(extra="allow")

    customer_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    tier: str = Field(default="Standard")  # VIP, Standard, Gold
    history_summary: str = Field(default="")
    email: str | None = None
    total_orders: int = Field(default=0, ge=0)
    total_spent_inr: float = Field(default=0.0, ge=0.0)
    notes: str = Field(default="")


class CustomerOrder(BaseModel):
    """Individual customer order record for resolution actions."""

    model_config = ConfigDict(extra="allow")

    order_id: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    product_id: str = Field(min_length=1)
    order_date: str = Field(min_length=1)
    price: float = Field(gt=0.0)
    status: str = Field(default="processing")  # processing, shipped, delivered, cancelled, refunded
    fulfillment_status: str = Field(default="pending")  # pending, in_transit, delivered, unfulfilled
    issue_information: str = Field(default="None")
    refund_state: str = Field(default="none")  # none, eligible, requested, pending_approval, completed, rejected
    replacement_state: str = Field(default="none")  # none, eligible, requested, completed, blocked_out_of_stock
    cancellation_state: str = Field(default="none")  # none, eligible, requested, completed, blocked_shipped
