"""In-memory run manager and API router for agent investigations."""

import logging
import threading
from decimal import Decimal
from time import monotonic
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.agent.controller import AgentController
from backend.agent.decisions import EvidenceBasedDecisionProvider, LLMDecisionProvider
from backend.config import get_settings
from backend.data.database import SimulatedCompanyRepository
from backend.data.scenarios import SCENARIOS
from backend.llm.client import LLMClient
from backend.llm.provider import LLMProviderError, build_llm_provider
from backend.models.agent import AgentState
from backend.models.events import AgentEvent
from backend.tools.actions import ActionRegistry
from backend.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

class CreateRunRequest(BaseModel):
    goal: str = Field(min_length=1)
    scenario: str = Field(default="inventory_supplier_failure")
    approval_threshold_inr: Decimal = Field(default=Decimal("50000"))
    step_delay_seconds: float = Field(default=0.5, ge=0.0, le=5.0)


class ApprovalDecisionRequest(BaseModel):
    approved: bool
    step_delay_seconds: float = Field(default=0.5, ge=0.0, le=5.0)


class ScenarioInfo(BaseModel):
    key: str
    name: str
    description: str


router = APIRouter(prefix="", tags=["investigations"])

# In-memory store mapping run_id -> (AgentController, AgentState, per-run state lock).
# The lock guards every mutation of the AgentState made by the background investigation
# thread, and every read/serialize of that same state made by a concurrent API request
# (GET /runs/{id}), so poll responses can never observe a half-updated (torn) state.
_RunLock = type(threading.RLock())
_RUNS: dict[str, tuple[AgentController, AgentState, _RunLock]] = {}


def _create_controller(scenario_key: str, threshold: Decimal) -> tuple[AgentController, SimulatedCompanyRepository]:
    repo = SimulatedCompanyRepository(scenario_key)
    tool_registry = ToolRegistry(repo)
    action_registry = ActionRegistry(repo, threshold)

    settings = get_settings()
    provider = None
    if settings.llm_is_configured:
        try:
            llm_provider = build_llm_provider(settings)
            client = LLMClient.from_settings(settings, llm_provider)
            provider = LLMDecisionProvider(client)
        except LLMProviderError as error:
            # An LLM was requested but can't actually be reached/configured correctly.
            # Fail loudly in the logs (so misconfiguration is visible) and fall back to the
            # deterministic rule-based provider rather than pretending LLM mode is active.
            logger.warning("LLM provider unavailable, falling back to rule-based decisions: %s", error)

    if provider is None:
        provider = EvidenceBasedDecisionProvider()

    controller = AgentController(tool_registry, provider, action_registry=action_registry)
    return controller, repo


@router.get("/scenarios", response_model=list[ScenarioInfo])
def list_scenarios() -> list[ScenarioInfo]:
    """Return available deterministic simulation scenarios."""
    return [
        ScenarioInfo(key=sc.key, name=sc.name, description=sc.description)
        for sc in SCENARIOS.values()
    ]


from backend.models.agent import CustomerCase


def _build_customer_case(scenario_key: str) -> CustomerCase:
    cases = {
        "deployment_service_failure": CustomerCase(
            case_id="CS-10482",
            issue="Customer unable to complete checkout after release.",
            impact="HIGH",
            affected_service="Checkout Service",
            status="INVESTIGATING",
        ),
        "inventory_supplier_failure": CustomerCase(
            case_id="CS-10390",
            issue="Best-seller stockout due to delayed supplier shipment.",
            impact="HIGH",
            affected_service="Inventory & Order Fulfillment",
            status="INVESTIGATING",
        ),
        "payment_failure": CustomerCase(
            case_id="CS-10415",
            issue="Payment gateway timeout surge during transaction.",
            impact="HIGH",
            affected_service="Payment Gateway",
            status="INVESTIGATING",
        ),
        "misleading_initial_hypothesis": CustomerCase(
            case_id="CS-10450",
            issue="Shipping fee spike causing elevated cart abandonment.",
            impact="MEDIUM",
            affected_service="Pricing & Shipping Service",
            status="INVESTIGATING",
        ),
    }
    return cases.get(
        scenario_key,
        CustomerCase(
            case_id="CS-10000",
            issue="Reported operational anomaly.",
            impact="MEDIUM",
            affected_service="Core Platform",
            status="INVESTIGATING",
        ),
    )


@router.post("/runs", response_model=AgentState)
def start_run(request: CreateRunRequest) -> AgentState:
    """Start a new agent investigation run."""
    if not isinstance(request.goal, str) or not request.goal.strip():
        raise HTTPException(status_code=400, detail="Provide a non-empty operational investigation goal.")
    if request.scenario not in SCENARIOS:
        raise HTTPException(status_code=400, detail=f"Unknown scenario '{request.scenario}'.")

    controller, _ = _create_controller(request.scenario, request.approval_threshold_inr)
    customer_case = _build_customer_case(request.scenario)
    lock = threading.RLock()

    if request.step_delay_seconds > 0:
        from backend.agent.events import record_event
        state = AgentState(original_goal=request.goal.strip(), customer_case=customer_case)
        record_event(state, "decision", f"Investigation initialized for goal: {state.original_goal}")
        _RUNS[state.run_id] = (controller, state, lock)

        def worker():
            controller._run_loop(state, monotonic(), step_delay=request.step_delay_seconds, lock=lock)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        with lock:
            return state.model_copy(deep=True)

    state = controller.run(request.goal, step_delay=0.0, lock=lock)
    state.customer_case = customer_case
    _RUNS[state.run_id] = (controller, state, lock)
    return state


@router.get("/runs/{run_id}", response_model=AgentState)
def get_run_state(run_id: str) -> AgentState:
    """Retrieve the current state of an investigation run.

    Takes the run's lock before copying so a poll can never observe a state mid-mutation
    from the background investigation thread (see the note on ``_RUNS`` above).
    """
    if run_id not in _RUNS:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
    _, state, lock = _RUNS[run_id]
    with lock:
        return state.model_copy(deep=True)


@router.get("/runs/{run_id}/events", response_model=list[AgentEvent])
def get_run_events(run_id: str) -> list[AgentEvent]:
    """Retrieve structured execution timeline events for a run."""
    if run_id not in _RUNS:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
    _, state, lock = _RUNS[run_id]
    with lock:
        return list(state.events)


@router.post("/runs/{run_id}/approval", response_model=AgentState)
def submit_approval(run_id: str, decision: ApprovalDecisionRequest) -> AgentState:
    """Submit a human approval decision for a pending high-risk action."""
    if run_id not in _RUNS:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
    controller, state, lock = _RUNS[run_id]
    with lock:
        if state.status != "awaiting_approval":
            raise HTTPException(status_code=400, detail="Run is not awaiting human approval.")

    if decision.step_delay_seconds > 0:
        with lock:
            state.status = "running"
            snapshot = state.model_copy(deep=True)

        def worker():
            controller.resume_after_approval(state, approved=decision.approved, step_delay=decision.step_delay_seconds, lock=lock)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        return snapshot

    updated_state = controller.resume_after_approval(state, approved=decision.approved, step_delay=0.0, lock=lock)
    _RUNS[run_id] = (controller, updated_state, lock)
    return updated_state
