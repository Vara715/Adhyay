"""Single-controller investigation loop with safe stopping, permission-gated actions, and
mandatory post-action verification."""

from contextlib import nullcontext
from threading import RLock as _RLockFactory
from time import monotonic
from typing import Any

RLockType = type(_RLockFactory())

from pydantic import ValidationError

from backend.agent.decisions import AgentDecisionProvider
from backend.agent.events import record_event
from backend.agent.state import (
    ActionProposal,
    AgentState,
    EvidenceItem,
    FinalResult,
    ToolHistoryEntry,
    failed_state,
)
from backend.llm.provider import LLMProviderError
from backend.models.agent import AgentDecision, AgentStatus
from backend.models.tools import ToolResult
from backend.tools.actions import ActionRegistry
from backend.tools.registry import ToolRegistry


class AgentController:
    """Runs Goal → Decide → Tool/Action → Observe → Evaluate → Adapt/Complete for one session.

    Permission enforcement lives here, not in the decision provider: every action decision is
    routed through ``ActionRegistry.propose``, which independently computes the permission level
    from the validated arguments. A high-risk action can never execute without an ``approved``
    status set via :meth:`resume_after_approval` — the loop halts and returns control to the
    caller the moment such a proposal is created, and never calls the decision provider again
    until a human decision is supplied.

    No executed action is ever reported as successful without confirmation: every action that
    actually runs (auto-executed low-risk, or approved high-risk) is immediately followed by a
    baseline-vs-after comparison via :meth:`ActionRegistry.verify`, and any outcome other than
    ``"verified"`` is recorded in ``state.verification_notes`` so it always surfaces in the final
    report's ``unresolved_issues`` — regardless of what the decision provider's own conclusion
    text claims.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        decision_provider: AgentDecisionProvider,
        *,
        action_registry: ActionRegistry | None = None,
        max_steps: int = 10,
        timeout_seconds: float = 30.0,
    ) -> None:
        if max_steps < 1:
            raise ValueError("max_steps must be at least 1.")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than 0.")
        self._registry = registry
        self._decision_provider = decision_provider
        self._action_registry = action_registry
        self._max_steps = max_steps
        self._timeout_seconds = timeout_seconds

    def _available_tools(self) -> list:
        """Merge read-only and action tool metadata so a real LLM can see and call both.

        Previously only ``registry.discover()`` (read-only tools) was ever sent to the
        decision provider, so an LLM-driven run had no way to even know remediation actions
        (create_purchase_request, rollback_deployment, create_support_ticket,
        request_human_approval) existed as callable tools.
        """
        tools = list(self._registry.discover())
        if self._action_registry is not None:
            tools.extend(self._action_registry.discover())
        return tools

    def run(self, goal: str, step_delay: float = 0.0, lock: RLockType | None = None) -> AgentState:
        """Start a new investigation from a raw goal."""
        if not isinstance(goal, str) or not goal.strip():
            return failed_state(str(goal), "Provide a non-empty operational investigation goal.")

        state = AgentState(original_goal=goal.strip())
        record_event(state, "decision", f"Investigation initialized for goal: {state.original_goal}")
        return self._run_loop(state, monotonic(), step_delay=step_delay, lock=lock)

    def resume_after_approval(
        self, state: AgentState, *, approved: bool, step_delay: float = 0.0, lock: RLockType | None = None
    ) -> AgentState:
        """Resolve the one pending high-risk action and continue the same investigation."""
        if state.status != "awaiting_approval" or state.pending_action is None:
            raise ValueError("No pending high-risk action is awaiting human approval.")
        if self._action_registry is None:
            raise ValueError("Action execution is not configured for this session.")

        guard = lock or nullcontext()
        proposal = state.pending_action
        with guard:
            if approved:
                self._action_registry.approve(proposal)
                baseline = self._action_registry.capture_baseline(proposal)
                result = self._action_registry.execute(proposal)
                self._record_action_result(state, proposal, result)
                if result.ok:
                    self._verify_action(state, proposal, baseline)
            else:
                self._action_registry.reject(proposal)
                state.actions.append(f"{proposal.action}: rejected by human reviewer.")
                record_event(
                    state, "adaptation",
                    f"{proposal.action} was rejected; continuing within remaining authority.",
                    proposal.action,
                )

            state.pending_action = None
            state.status = "running"
        return self._run_loop(state, monotonic(), step_delay=step_delay, lock=lock)

    def _run_loop(self, state: AgentState, started: float, step_delay: float = 0.0, lock: RLockType | None = None) -> AgentState:
        import time

        guard = lock or nullcontext()

        while state.step_count < self._max_steps:
            if monotonic() - started > self._timeout_seconds:
                with guard:
                    return self._stop(state, "timed_out", "Investigation stopped because the configured time limit was reached.")
            try:
                # Decision-provider calls (especially a real LLM over the network) can be slow;
                # deliberately kept outside the lock so concurrent state reads (e.g. API polling)
                # are never blocked for the duration of a model round-trip.
                raw_decision = self._decision_provider.decide(state, self._available_tools())
                decision = raw_decision if isinstance(raw_decision, AgentDecision) else AgentDecision.model_validate(raw_decision)
            except (ValidationError, TypeError, ValueError) as error:
                with guard:
                    return self._stop(state, "failed", f"Malformed decision response: {error}")
            except LLMProviderError as error:
                with guard:
                    return self._stop(
                        state, "failed",
                        f"The configured LLM endpoint could not be reached or returned an invalid response: {error}",
                    )
            except Exception:
                with guard:
                    return self._stop(state, "failed", "The investigation decision provider failed unexpectedly.")

            if monotonic() - started > self._timeout_seconds:
                with guard:
                    return self._stop(state, "timed_out", "Investigation stopped because the configured time limit was reached.")

            with guard:
                prior_hypothesis = state.current_hypothesis
                self._record_adaptation_if_needed(state, decision)
                target_name = self._decision_target_name(decision)
                record_event(state, "decision", f"Selected {target_name or 'completion'}: {decision.reasoning}", target_name)
                state.current_objective = decision.current_objective
                state.current_hypothesis = decision.hypothesis
                if decision.hypothesis != prior_hypothesis:
                    record_event(state, "hypothesis_update", f"Hypothesis updated: {decision.hypothesis}")
                    state.evidence.append(EvidenceItem(source="Agent Reasoning", fact=decision.hypothesis, kind="hypothesis"))

                state.step_count += 1

                if decision.kind == "finish":
                    state.status = "completed"
                    if state.customer_case:
                        state.customer_case.status = "RESOLVED"
                    state.final_result = FinalResult(
                        conclusion=decision.conclusion or "Investigation completed without a conclusion.",
                        confidence=decision.confidence,
                        unresolved_issues=list(state.verification_notes),
                        actions_executed=list(state.actions),
                    )
                    record_event(state, "completed", decision.conclusion or "Investigation completed.")
                    return state

                if decision.kind == "action":
                    halted = self._handle_action(state, decision)
                    action_continues = halted is None
                else:
                    action_continues = False
                    record_event(state, "tool_call", f"Calling {decision.tool_call.name}.", decision.tool_call.name)
                    result = self._registry.execute(decision.tool_call)
                    step = len(state.tool_history) + 1
                    state.tool_history.append(ToolHistoryEntry(
                        step=step, reasoning=decision.reasoning, hypothesis=decision.hypothesis,
                        tool_call=decision.tool_call, result=result,
                    ))
                    if result.ok:
                        state.evidence.append(EvidenceItem(source=result.tool_name, fact=result.summary, kind="fact"))
                        record_event(state, "tool_result", result.summary, result.tool_name)
                        for warning in result.warnings:
                            state.evidence.append(EvidenceItem(
                                source=result.tool_name,
                                fact=f"Data quality warning ({warning.code}): {warning.message}",
                                kind="fact",
                            ))
                    else:
                        failure = result.error.message if result.error else result.summary
                        state.failures.append(f"{result.tool_name}: {failure}")
                        state.evidence.append(EvidenceItem(source=result.tool_name, fact=f"Tool unavailable or invalid: {failure}", kind="fact"))
                        record_event(state, "tool_error", failure, result.tool_name)

                if decision.kind == "action" and not action_continues:
                    return halted

            if step_delay > 0 and state.status == "running":
                time.sleep(step_delay)

        with guard:
            return self._stop(state, "step_limit_reached", "Investigation stopped because the maximum step limit was reached.")

    def _handle_action(self, state: AgentState, decision: AgentDecision) -> AgentState | None:
        """Propose, permission-gate, and (if allowed) execute-and-verify one action.

        Returns a halted state when the action requires human approval or cannot proceed;
        returns ``None`` to let the loop continue when the action ran (or was safely rejected
        as invalid) without needing to pause.
        """
        if self._action_registry is None:
            return self._stop(state, "failed", "Action execution is not configured for this session.")

        evidence_refs = [item.fact for item in state.evidence]
        proposal = self._action_registry.propose(
            decision.action_call.name, decision.action_call.arguments,
            reason=decision.reasoning, evidence=evidence_refs,
        )
        if isinstance(proposal, ToolResult):
            failure = proposal.error.message if proposal.error else proposal.summary
            state.failures.append(f"{decision.action_call.name}: {failure}")
            record_event(state, "tool_error", failure, decision.action_call.name)
            return None

        state.action_proposals.append(proposal)
        record_event(
            state, "action_proposed",
            f"Proposed {proposal.action} ({proposal.permission_level.replace('_', ' ')}): {proposal.reason}",
            proposal.action,
        )

        if proposal.permission_level == "high_risk":
            state.pending_action = proposal
            state.status = "awaiting_approval"
            record_event(state, "approval_required", f"{proposal.action} requires human approval before it can run.", proposal.action)
            return state

        baseline = self._action_registry.capture_baseline(proposal)
        result = self._action_registry.execute(proposal)
        self._record_action_result(state, proposal, result)
        if result.ok:
            self._verify_action(state, proposal, baseline)
        return None

    def _verify_action(self, state: AgentState, proposal: ActionProposal, baseline: dict[str, Any]) -> None:
        """Query the relevant system again and compare against the pre-action baseline.

        The action is never assumed to have worked just because it executed: only a
        ``"verified"`` outcome is treated as confirmed. ``"failed"`` and ``"inconclusive"``
        outcomes are both recorded as unresolved so they cannot be silently dropped from the
        final report.
        """
        outcome = self._action_registry.verify(proposal, baseline)
        proposal.verification = outcome
        proposal.outcome_summary = f"Executed; verification {outcome.status}: {outcome.detail}"
        record_event(state, "verification", f"{proposal.action} verification {outcome.status}: {outcome.detail}", proposal.action)
        if outcome.status == "verified":
            state.evidence.append(EvidenceItem(source="Post-Action Verification", fact=f"Verified {proposal.action}: {outcome.detail}", kind="verified"))
        else:
            state.verification_notes.append(f"{proposal.action}: {outcome.detail}")

    @staticmethod
    def _record_action_result(state: AgentState, proposal: ActionProposal, result: ToolResult) -> None:
        """Record an executed action's true outcome; never assume it succeeded."""
        state.actions.append(f"{proposal.action}: {result.summary}")
        if result.ok:
            record_event(state, "action_executed", result.summary, proposal.action)
        else:
            state.failures.append(f"{proposal.action}: {result.summary}")
            record_event(state, "tool_error", result.summary, proposal.action)

    @staticmethod
    def _decision_target_name(decision: AgentDecision) -> str | None:
        if decision.tool_call:
            return decision.tool_call.name
        if decision.action_call:
            return decision.action_call.name
        return None

    @staticmethod
    def _stop(state: AgentState, status: AgentStatus, message: str) -> AgentState:
        state.status = status
        if state.customer_case:
            state.customer_case.status = "ESCALATED"
        state.failures.append(message)
        state.final_result = FinalResult(
            conclusion=message,
            confidence="low",
            unresolved_issues=[message, *state.verification_notes],
            actions_executed=list(state.actions),
        )
        return state

    @classmethod
    def _record_adaptation_if_needed(cls, state: AgentState, decision: AgentDecision) -> None:
        """Record a concise strategy change after failed or low-quality evidence."""
        if not state.tool_history:
            return
        previous = state.tool_history[-1]
        next_name = cls._decision_target_name(decision) or "a safe completion"
        if not previous.result.ok:
            record_event(
                state,
                "adaptation",
                f"{previous.result.tool_name} failed; switching to {next_name} without assuming missing data.",
                cls._decision_target_name(decision),
            )
        elif previous.result.warnings:
            warning_types = ", ".join(warning.code for warning in previous.result.warnings)
            if decision.kind == "finish":
                summary = (
                    f"{previous.result.tool_name} returned {warning_types}; "
                    "the remaining aggregate evidence is sufficient for a safe completion."
                )
            else:
                summary = (
                    f"{previous.result.tool_name} returned {warning_types}; "
                    f"seeking corroborating evidence with {next_name}."
                )
            record_event(
                state,
                "adaptation",
                summary,
                cls._decision_target_name(decision),
            )
