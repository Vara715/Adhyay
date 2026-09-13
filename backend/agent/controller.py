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
from backend.models.agent import AgentDecision, AgentStatus, CustomerCase
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

    def run(
        self,
        goal: str,
        step_delay: float = 0.0,
        lock: RLockType | None = None,
        customer_case: CustomerCase | None = None,
    ) -> AgentState:
        """Start a new investigation from a raw goal."""
        if not isinstance(goal, str) or not goal.strip():
            return failed_state(str(goal), "Provide a non-empty operational investigation goal.")

        case = customer_case or self._init_customer_case(goal.strip())
        state = AgentState(original_goal=goal.strip(), customer_case=case)
        record_event(state, "decision", f"Investigation initialized for goal: {state.original_goal}")
        return self._run_loop(state, monotonic(), step_delay=step_delay, lock=lock)

    @staticmethod
    def _init_customer_case(goal: str) -> CustomerCase:
        import re
        from uuid import uuid4
        from backend.models.agent import CustomerCase

        order_match = re.search(r"ORD-\d+", goal, re.IGNORECASE)
        customer_match = re.search(r"CUST-\d+", goal, re.IGNORECASE)
        order_id = order_match.group(0).upper() if order_match else None
        customer_id = customer_match.group(0).upper() if customer_match else None

        case_id = f"CASE-{order_id}" if order_id else f"CS-{uuid4().hex[:6].upper()}"

        goal_lower = goal.lower()
        requested_res = None
        if "refund" in goal_lower or "money back" in goal_lower or "return" in goal_lower:
            requested_res = "refund"
        elif "cancel" in goal_lower or "cancellation" in goal_lower:
            requested_res = "cancellation"
        elif "replace" in goal_lower or "replacement" in goal_lower:
            requested_res = "replacement"

        return CustomerCase(
            case_id=case_id,
            customer_id=customer_id,
            order_id=order_id,
            original_goal=goal,
            issue=goal,
            requested_resolution=requested_res,
            status="OPEN",
        )

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
                if state.customer_case:
                    state.customer_case.status = "ACTION_IN_PROGRESS"
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

        with guard:
            if state.customer_case:
                if state.customer_case.status == "OPEN":
                    state.customer_case.status = "INVESTIGATING"
                state.customer_case.original_goal = state.original_goal
                state.customer_case.evidence = [item.fact for item in state.evidence]
                state.customer_case.actions = list(state.actions)

        while state.step_count < self._max_steps:
            if monotonic() - started > self._timeout_seconds:
                with guard:
                    return self._stop(state, "timed_out", "Investigation stopped because the configured time limit was reached.")
            try:
                raw_decision = self._decision_provider.decide(state, self._available_tools())
                decision = raw_decision if isinstance(raw_decision, AgentDecision) else AgentDecision.model_validate(raw_decision)
            except (ValidationError, TypeError, ValueError, LLMProviderError) as error:
                from backend.agent.decisions import LLMDecisionProvider, EvidenceBasedDecisionProvider
                if isinstance(self._decision_provider, LLMDecisionProvider):
                    record_event(
                        state, "adaptation",
                        f"LLM decision provider encountered an issue ({error}). Falling back to rule-based decision engine.",
                        None,
                    )
                    self._decision_provider = EvidenceBasedDecisionProvider()
                    raw_decision = self._decision_provider.decide(state, self._available_tools())
                    decision = raw_decision if isinstance(raw_decision, AgentDecision) else AgentDecision.model_validate(raw_decision)
                else:
                    with guard:
                        return self._stop(state, "failed", f"Malformed decision response: {error}")
            except Exception as error:
                from backend.agent.decisions import LLMDecisionProvider, EvidenceBasedDecisionProvider
                if isinstance(self._decision_provider, LLMDecisionProvider):
                    record_event(
                        state, "adaptation",
                        f"LLM decision provider error ({error}). Falling back to rule-based decision engine.",
                        None,
                    )
                    self._decision_provider = EvidenceBasedDecisionProvider()
                    raw_decision = self._decision_provider.decide(state, self._available_tools())
                    decision = raw_decision if isinstance(raw_decision, AgentDecision) else AgentDecision.model_validate(raw_decision)
                else:
                    with guard:
                        return self._stop(state, "failed", f"The investigation decision provider failed unexpectedly: {error}")

            if monotonic() - started > self._timeout_seconds:
                with guard:
                    return self._stop(state, "timed_out", "Investigation stopped because the configured time limit was reached.")

            with guard:
                prior_hypothesis = state.current_hypothesis
                target_name = self._decision_target_name(decision)

                if "adapt" in decision.reasoning.lower() or "adapt" in decision.current_objective.lower():
                    state.adaptation_required = True
                    state.previous_plan = state.current_objective
                    state.adaptation_reason = decision.reasoning
                    state.adaptation_count += 1
                    if target_name and target_name not in state.alternatives_considered:
                        state.alternatives_considered.append(target_name)
                    if state.customer_case:
                        state.customer_case.adaptation_count = state.adaptation_count
                        state.customer_case.adaptation_summary = decision.reasoning
                    record_event(state, "adaptation", f"Adaptive strategy update #{state.adaptation_count}: {decision.reasoning}", target_name)
                else:
                    self._record_adaptation_if_needed(state, decision)

                from backend.agent.decisions import LLMDecisionProvider
                is_llm = isinstance(self._decision_provider, LLMDecisionProvider)
                event_type = "llm_decision" if is_llm else "decision"
                prefix = "LLM selected" if is_llm else "Rule-based policy selected"
                record_event(state, event_type, f"{prefix} {target_name or 'completion'}: {decision.reasoning}", target_name)
                state.current_objective = decision.current_objective
                state.current_hypothesis = decision.hypothesis
                if decision.hypothesis != prior_hypothesis:
                    record_event(state, "hypothesis_update", f"Hypothesis updated: {decision.hypothesis}")
                    state.evidence.append(EvidenceItem(source="Agent Reasoning", fact=decision.hypothesis, kind="hypothesis"))

                state.step_count += 1

                if decision.kind == "finish":
                    state.status = "completed"
                    if state.customer_case:
                        state.customer_case.evidence = [item.fact for item in state.evidence]
                        state.customer_case.actions = list(state.actions)
                        state.customer_case.unresolved_issues = list(state.verification_notes)

                        has_unverified = bool(state.verification_notes) or any(
                            p.verification and p.verification.status != "verified"
                            for p in state.action_proposals
                            if p.approval_status == "executed"
                        )
                        has_escalation = any(
                            p.action == "escalate_customer_case"
                            for p in state.action_proposals
                            if p.approval_status == "executed"
                        )
                        has_executed_action = any(
                            p.approval_status == "executed" for p in state.action_proposals
                        )

                        if has_unverified:
                            # CRITICAL RULE: Never mark RESOLVED if verification failed/inconclusive!
                            state.customer_case.status = "FAILED"
                            state.customer_case.final_resolution = "Resolution unconfirmed: verification failed or incomplete."
                        elif has_escalation:
                            state.customer_case.status = "ESCALATED"
                            state.customer_case.escalation_reason = decision.conclusion
                            state.customer_case.final_resolution = decision.conclusion
                        elif state.customer_case.requested_resolution and not has_executed_action:
                            # CRITICAL RULE: Never mark RESOLVED if no remediation action was executed for requested resolution
                            state.customer_case.status = "FAILED"
                            state.customer_case.unresolved_issues.append("No remediation action was executed for requested resolution.")
                            state.customer_case.final_resolution = "Resolution incomplete: no remediation action executed."
                        else:
                            # CRITICAL RULE SATISFIED: Objective completed, expected state changed, verification succeeded
                            state.customer_case.status = "RESOLVED"
                            state.customer_case.final_resolution = decision.conclusion or "Customer issue resolved successfully."


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
            if state.customer_case:
                state.customer_case.status = "AWAITING_APPROVAL"
            record_event(state, "approval_required", f"{proposal.action} requires human approval before it can run.", proposal.action)
            return state

        if state.customer_case:
            state.customer_case.status = "ACTION_IN_PROGRESS"

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
        if state.customer_case:
            state.customer_case.status = "VERIFYING"

        outcome = self._action_registry.verify(proposal, baseline)
        proposal.verification = outcome
        proposal.outcome_summary = f"Executed; verification {outcome.status}: {outcome.detail}"
        if state.customer_case:
            state.customer_case.verification_results.append(
                f"{proposal.action} verification {outcome.status}: {outcome.detail}"
            )
        record_event(state, "verification", f"{proposal.action} verification {outcome.status}: {outcome.detail}", proposal.action)

        if outcome.status == "verified":
            state.evidence.append(EvidenceItem(source="Post-Action Verification", fact=f"Verified {proposal.action}: {outcome.detail}", kind="verified"))
            if state.customer_case:
                state.customer_case.evidence.append(f"Verified {proposal.action}: {outcome.detail}")
        else:
            state.adaptation_required = True
            state.failed_constraint = f"{proposal.action} verification {outcome.status}: {outcome.detail}"
            state.previous_plan = state.current_objective
            state.adaptation_reason = f"Verification {outcome.status} for action {proposal.action}"
            state.adaptation_count += 1
            state.verification_notes.append(f"{proposal.action}: {outcome.detail}")
            if state.customer_case:
                state.customer_case.adaptation_count = state.adaptation_count
                state.customer_case.adaptation_summary = f"Verification {outcome.status} for {proposal.action}"
                state.customer_case.unresolved_issues.append(
                    f"{proposal.action}: verification {outcome.status} - {outcome.detail}"
                )
                state.customer_case.status = "INVESTIGATING"

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
            if status in ("timed_out", "failed", "step_limit_reached"):
                state.customer_case.status = "FAILED"
            else:
                state.customer_case.status = "ESCALATED"
            state.customer_case.unresolved_issues = [message, *state.verification_notes]
            state.customer_case.final_resolution = message

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
            state.adaptation_required = True
            state.failed_constraint = f"Tool failure in {previous.result.tool_name}"
            state.previous_plan = state.current_objective
            state.adaptation_count += 1
            if state.customer_case:
                state.customer_case.adaptation_count = state.adaptation_count
                state.customer_case.adaptation_summary = f"{previous.result.tool_name} failed; adapted plan to {next_name}"
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
