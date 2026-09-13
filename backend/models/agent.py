"""Typed session state and decisions for the single investigation controller."""

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.models.actions import ActionCall, ActionProposal
from backend.models.attachments import EvidenceAttachment
from backend.models.events import AgentEvent
from backend.models.evidence import ClaimAssessment
from backend.models.tools import ToolCall, ToolResult

AgentStatus = Literal[
    "running", "awaiting_approval", "completed", "failed", "timed_out", "step_limit_reached",
]

CustomerCaseStatus = Literal[
    "OPEN",
    "INVESTIGATING",
    "AWAITING_APPROVAL",
    "ACTION_IN_PROGRESS",
    "VERIFYING",
    "RESOLVED",
    "ESCALATED",
    "FAILED",
]


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    fact: str
    kind: Literal["fact", "hypothesis", "verified"] = "fact"


class CustomerCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    customer_id: str | None = None
    order_id: str | None = None
    original_goal: str = ""
    issue: str = ""
    requested_resolution: str | None = None
    status: CustomerCaseStatus = "OPEN"
    evidence: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    verification_results: list[str] = Field(default_factory=list)
    unresolved_issues: list[str] = Field(default_factory=list)
    escalation_reason: str | None = None
    final_resolution: str | None = None

    # Attachments & Multimodal Claim Validation
    attachments: list[EvidenceAttachment] = Field(default_factory=list)
    claim_assessment: ClaimAssessment | None = None

    # Explicit Adaptation Tracking
    adaptation_count: int = 0
    adaptation_summary: str | None = None

    # Preserved for backward compatibility
    impact: str = "HIGH"
    affected_service: str = "Operational Service"


class ToolHistoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step: int
    reasoning: str
    hypothesis: str
    tool_call: ToolCall
    result: ToolResult


class FinalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conclusion: str
    confidence: Literal["low", "medium", "high"]
    unresolved_issues: list[str] = Field(default_factory=list)
    actions_executed: list[str] = Field(default_factory=list)


class AgentState(BaseModel):
    """Lightweight per-run state. It is intentionally not long-term memory."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(default_factory=lambda: str(uuid4()))
    original_goal: str
    customer_case: CustomerCase | None = None
    current_objective: str = "Understand the reported operational issue."
    current_hypothesis: str = "No hypothesis established."
    evidence: list[EvidenceItem] = Field(default_factory=list)
    tool_history: list[ToolHistoryEntry] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    action_proposals: list[ActionProposal] = Field(default_factory=list)
    pending_action: ActionProposal | None = None
    verification_notes: list[str] = Field(default_factory=list)
    events: list[AgentEvent] = Field(default_factory=list)
    status: AgentStatus = "running"
    final_result: FinalResult | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    step_count: int = 0

    # Attachments & Multimodal Claim Validation
    attachments: list[EvidenceAttachment] = Field(default_factory=list)
    claim_assessment: ClaimAssessment | None = None

    # Explicit Decision Source & LLM Provider Tracking
    decision_source: Literal["GROQ_LLM", "RULE_BASED_FALLBACK"] = "RULE_BASED_FALLBACK"
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_success: bool = False
    fallback_reason: str | None = None
    latency_ms: float | None = None
    decision_timestamp: datetime | None = None

    # Explicit Adaptation Tracking
    adaptation_required: bool = False
    adaptation_reason: str | None = None
    previous_plan: str | None = None
    failed_constraint: str | None = None
    adaptation_count: int = 0
    alternatives_considered: list[str] = Field(default_factory=list)


class AgentDecision(BaseModel):
    """A structured next step from an LLM or local decision policy."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["tool", "action", "finish"]
    current_objective: str = Field(min_length=1)
    hypothesis: str = Field(min_length=1)
    reasoning: str = Field(min_length=1)
    tool_call: ToolCall | None = None
    action_call: ActionCall | None = None
    conclusion: str | None = None
    confidence: Literal["low", "medium", "high"] = "medium"

    @model_validator(mode="after")
    def validate_shape(self) -> "AgentDecision":
        if self.kind == "tool" and self.tool_call is None:
            raise ValueError("Tool decisions require a tool_call.")
        if self.kind == "action" and self.action_call is None:
            raise ValueError("Action decisions require an action_call.")
        if self.kind == "finish" and not self.conclusion:
            raise ValueError("Finish decisions require a conclusion.")
        return self


def failed_state(goal: str, message: str) -> AgentState:
    """Construct a safe terminal state for invalid requests or controller failures."""
    return AgentState(
        original_goal=goal,
        status="failed",
        failures=[message],
        final_result=FinalResult(conclusion=message, confidence="low", unresolved_issues=[message]),
    )
