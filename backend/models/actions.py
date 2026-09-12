"""Schemas for safe simulated actions and human approval."""

from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

PermissionLevel = Literal["read_only", "low_risk", "high_risk"]
ApprovalStatus = Literal["not_required", "pending", "approved", "rejected", "executed", "failed"]
VerificationStatus = Literal["verified", "failed", "inconclusive"]


class ActionCall(BaseModel):
    """A provider-neutral request to invoke one registered action tool."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


class VerificationOutcome(BaseModel):
    """The result of comparing the relevant system's state before and after an action ran."""

    model_config = ConfigDict(extra="forbid")

    status: VerificationStatus
    detail: str
    before: dict[str, Any] = Field(default_factory=dict)
    after: dict[str, Any] = Field(default_factory=dict)


class ActionProposal(BaseModel):
    """A complete, reviewable record created before any action can run."""

    model_config = ConfigDict(extra="forbid")

    action_id: str = Field(default_factory=lambda: str(uuid4()))
    action: str
    arguments: dict[str, Any]
    reason: str
    evidence: list[str]
    estimated_impact: dict[str, Any]
    risk: str
    permission_level: PermissionLevel
    approval_status: ApprovalStatus
    outcome_summary: str | None = None
    verification: VerificationOutcome | None = None
