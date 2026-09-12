"""Typed session state and decisions for the single investigation controller."""

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.models.actions import ActionCall, ActionProposal
from backend.models.events import AgentEvent
from backend.models.tools import ToolCall, ToolResult

AgentStatus = Literal[
    "running", "awaiting_approval", "completed", "failed", "timed_out", "step_limit_reached",
]


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    fact: str
    kind: Literal["fact", "hypothesis", "verified"] = "fact"


class CustomerCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    issue: str
    impact: str = "HIGH"
    affected_service: str = "Operational Service"
    status: str = "INVESTIGATING"


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
