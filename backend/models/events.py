"""Concise, user-safe execution events for one agent investigation."""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EventType = Literal[
    "decision",
    "tool_call",
    "tool_result",
    "tool_error",
    "hypothesis_update",
    "adaptation",
    "action_proposed",
    "approval_required",
    "action_executed",
    "verification",
    "completed",
]


class AgentEvent(BaseModel):
    """A chronological public summary, never a hidden reasoning trace."""

    model_config = ConfigDict(extra="forbid")

    sequence: int
    event_type: EventType
    summary: str = Field(min_length=1)
    tool_name: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
