"""Helpers for adding concise chronological events to an agent session."""

from backend.models.agent import AgentState
from backend.models.events import AgentEvent, EventType


def record_event(state: AgentState, event_type: EventType, summary: str, tool_name: str | None = None) -> None:
    """Append a public-safe event; summaries intentionally exclude hidden reasoning and raw data."""
    state.events.append(AgentEvent(
        sequence=len(state.events) + 1,
        event_type=event_type,
        summary=summary,
        tool_name=tool_name,
    ))
