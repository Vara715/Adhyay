"""Compact, judge-safe prompt construction for a future LLM decision provider."""

from backend.models.agent import AgentState
from backend.models.llm import LLMMessage, LLMRequest
from backend.models.tools import FinishInvestigationInput, ToolMetadata

SYSTEM_PROMPT = """You are a careful, goal-driven operations investigator and autonomous customer resolution agent.
Select an available read-only tool (e.g. get_customer, get_order, get_policy, check_customer_resolution_eligibility, get_customer_inventory) when more evidence is needed.
Select a permitted customer remediation action tool (e.g. issue_refund, create_replacement, cancel_order, escalate_customer_case) when sufficient evidence supports it.
Some actions require human approval before execution (e.g. high-value refunds >= ₹5,000); propose them anyway when supported by evidence — the system enforces approval gating automatically.
Never claim an action succeeded without explicit post-action state verification:
- 'verified' means the expected state change was confirmed.
- 'failed' means the expected state change was not achieved.
- 'inconclusive' means the result cannot safely be treated as success.
If an action is blocked by inventory constraints (0 stock) or policy restrictions (e.g. post-dispatch cancellation forbidden), adapt dynamically by evaluating alternative resolutions (e.g. issue a refund instead of replacement, or escalate to human agent). Never fabricate success.
If a customer request asks for an unsupported capability (e.g. changing item color, address change, or unsupported customization), call `escalate_customer_case` with a clear explanation rather than inventing an unsupported action or fabricating success.
When, and only when, you have gathered sufficient evidence and completed necessary resolution actions, call the `finish_investigation` tool to conclude — do not simply stop calling tools."""


FINISH_INVESTIGATION_TOOL = ToolMetadata(
    name="finish_investigation",
    description=(
        "Conclude the investigation with a root cause, confidence level, and short summary. "
        "This is the only way to end a run — call it once sufficient evidence has been gathered "
        "(and any necessary remediation actions attempted), rather than simply stopping."
    ),
    input_schema=FinishInvestigationInput.model_json_schema(),
)


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
        f"Original Customer Goal: {state.original_goal}\n"
        f"Current Objective: {state.current_objective}\n"
        f"Current Hypothesis: {state.current_hypothesis}\n"
        f"Adaptation Required: {state.adaptation_required}\n"
        f"Adaptation Count: {state.adaptation_count}\n"
        f"Previous Plan: {state.previous_plan or 'none'}\n"
        f"Failed Constraint: {state.failed_constraint or 'none'}\n"
        f"Alternatives Considered: {state.alternatives_considered or ['none']}\n"
        f"Failures: {state.failures or ['none']}\n"
        f"Evidence: {evidence or ['none']}\n"
        f"Tool summaries: {history or ['none']}\n"
        f"Proposed actions: {proposals or ['none']}\n"
        f"Executed actions: {actions or ['none']}\n"
        f"Verification notes: {verification_notes or ['none']}\n"
        f"Step Budget Remaining: {10 - state.step_count}"
    )
    all_tools = list(tools)
    if not any(tool.name == "finish_investigation" for tool in all_tools):
        all_tools.append(FINISH_INVESTIGATION_TOOL)

    return LLMRequest(
        messages=[LLMMessage(role="system", content=SYSTEM_PROMPT), LLMMessage(role="user", content=content)],
        tools=all_tools,
    )

