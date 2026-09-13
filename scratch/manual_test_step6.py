"""Real manual demo script executing Step 6 explicit adaptation flows."""

from decimal import Decimal
from backend.agent.controller import AgentController
from backend.agent.decisions import EvidenceBasedDecisionProvider
from backend.data.database import SimulatedCompanyRepository
from backend.tools.actions import ActionRegistry
from backend.tools.registry import ToolRegistry


def demo_stockout_adaptation():
    print("==================================================================")
    print("MANUAL DEMO 1: Stockout Adaptation (Replacement -> Refund)")
    print("==================================================================")
    repo = SimulatedCompanyRepository("customer_replacement_out_of_stock_adapts_refund")
    controller = AgentController(
        ToolRegistry(repo),
        EvidenceBasedDecisionProvider(),
        action_registry=ActionRegistry(repo, Decimal("50000")),
    )
    goal = "I received a damaged product in order ORD-9003 and would like a replacement."
    state = controller.run(goal)

    print(f"Original Customer Goal (Preserved): {state.original_goal}")
    print(f"Final Customer Case Status: {state.customer_case.status}")
    print(f"Adaptation Required: {state.adaptation_required}")
    print(f"Adaptation Count: {state.adaptation_count}")
    print(f"Previous Plan: {state.previous_plan}")
    print(f"Adaptation Reason: {state.adaptation_reason}")
    print(f"Alternatives Considered: {state.alternatives_considered}")
    print("\nRecorded Activity Events:")
    for e in state.events:
        print(f"  [{e.event_type.upper()}] {str(e.summary).replace('₹', 'INR ')}")
    print("\nActions Executed:")
    for a in state.actions:
        print(f"  - {a}")
    print(f"\nFinal Resolution: {str(state.customer_case.final_resolution).replace('₹', 'INR ')}")
    print()


def demo_policy_escalation():
    print("==================================================================")
    print("MANUAL DEMO 2: Policy Restriction Adaptation (Post-dispatch Cancellation -> Escalation)")
    print("==================================================================")
    repo = SimulatedCompanyRepository("customer_refund_denied_policy_escalation")
    controller = AgentController(
        ToolRegistry(repo),
        EvidenceBasedDecisionProvider(),
        action_registry=ActionRegistry(repo, Decimal("50000")),
    )
    goal = "I want to cancel my shipped order ORD-9004."
    state = controller.run(goal)

    print(f"Original Customer Goal (Preserved): {state.original_goal}")
    print(f"Final Customer Case Status: {state.customer_case.status}")
    print(f"Adaptation Required: {state.adaptation_required}")
    print(f"Adaptation Count: {state.adaptation_count}")
    print(f"Escalation Reason: {state.customer_case.escalation_reason}")
    print("\nRecorded Activity Events:")
    for e in state.events:
        print(f"  [{e.event_type.upper()}] {str(e.summary).replace('₹', 'INR ')}")
    print()


if __name__ == "__main__":
    demo_stockout_adaptation()
    demo_policy_escalation()
