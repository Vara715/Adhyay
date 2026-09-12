"""Compact, judge-safe prompt construction for a future LLM decision provider."""

from backend.models.agent import AgentState
from backend.models.llm import LLMMessage, LLMRequest
from backend.models.tools import ToolMetadata

SYSTEM_PROMPT = """You are a careful, goal-driven operations investigator and autonomous resolution agent.
Select an available read-only tool when more evidence is needed, or propose a permitted remediation action when sufficient evidence supports it.
Never claim an action succeeded without explicit verification:
- 'verified' means the expected state change was confirmed.
- 'failed' means the expected state change was not achieved.
- 'inconclusive' means the result cannot safely be treated as success.
If verification fails or is inconclusive, continue investigating or adapt with another permitted action.
Return a concise decision summary; never reveal private chain-of-thought."""


def build_decision_request(state: AgentState, tools: list[ToolMetadata]) -> LLMRequest:
    """Keep provider context small: summaries, evidence, actions, and verification status."""
    history = [
        f"{entry.tool_call.name}: {entry.result.summary}"
        for entry in state.tool_history[-8:]
    ]
    evidence = [item.fact for item in state.evidence[-8:]]
    actions = list(state.actions[-5:])
    proposals = [
        f"{p.action} (permission: {p.permission_level}, status: {p.approval_status})"
        for p in state.action_proposals[-5:]
    ]
    verification_notes = list(state.verification_notes[-5:])

    content = (
        f"Goal: {state.original_goal}\n"
        f"Objective: {state.current_objective}\n"
        f"Hypothesis: {state.current_hypothesis}\n"
        f"Evidence: {evidence or ['none']}\n"
        f"Tool summaries: {history or ['none']}\n"
        f"Proposed actions: {proposals or ['none']}\n"
        f"Executed actions: {actions or ['none']}\n"
        f"Verification notes: {verification_notes or ['none']}"
    )
    return LLMRequest(
        messages=[LLMMessage(role="system", content=SYSTEM_PROMPT), LLMMessage(role="user", content=content)],
        tools=tools,
    )

