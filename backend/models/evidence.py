"""Structured evidence record and claim assessment models."""

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

ClaimStatus = Literal["SUPPORTED", "CONTRADICTED", "INCONCLUSIVE", "NOT_EVALUATED"]


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str  # e.g. "customer_statement", "customer_image", "order_database", "warehouse_log", "shipment_log"
    claim: str   # e.g. "received_product", "order_status", "item_condition"
    value: str   # e.g. "Phone 2", "ORD-9002", "Damaged in transit"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ClaimAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_status: ClaimStatus = "NOT_EVALUATED"
    claimed_issue: str = ""
    expected_value: str | None = None
    observed_value: str | None = None
    reason: str = ""
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    auditable_summary: str = ""
