"""Real manual test script executing TEST A, TEST B, and TEST C for Step 4."""

from decimal import Decimal
from backend.agent.controller import AgentController
from backend.agent.decisions import EvidenceBasedDecisionProvider
from backend.data.database import SimulatedCompanyRepository
from backend.tools.actions import ActionRegistry
from backend.tools.registry import ToolRegistry


def run_test_a():
    print("==================================================================")
    print("REAL MANUAL TEST A: 'My laptop stand arrived damaged. I want a replacement.'")
    print("==================================================================")
    repo = SimulatedCompanyRepository("customer_damaged_replacement_available")
    controller = AgentController(
        ToolRegistry(repo),
        EvidenceBasedDecisionProvider(),
        action_registry=ActionRegistry(repo, Decimal("50000")),
    )
    goal = "My laptop stand arrived damaged in order ORD-9002. I want a replacement."
    state = controller.run(goal)
    print(f"Final State Status: {state.status}")
    print(f"Customer Case Status: {state.customer_case.status}")
    print(f"Customer Case Goal: {state.customer_case.original_goal}")
    print(f"Requested Resolution: {state.customer_case.requested_resolution}")
    print(f"Final Resolution: {str(state.customer_case.final_resolution).replace('₹', 'INR ')}")
    print("\nActions Executed:")
    for a in state.actions:
        print(f"  - {a}")
    print("\nVerification Results:")
    for v in state.customer_case.verification_results:
        print(f"  - {str(v).replace('₹', 'INR ')}")
    print()
    return state


def run_test_b():
    print("==================================================================")
    print("REAL MANUAL TEST B: 'My product arrived damaged. Please replace it.' (Stockout Scenario)")
    print("==================================================================")
    repo = SimulatedCompanyRepository("customer_replacement_out_of_stock_adapts_refund")
    controller = AgentController(
        ToolRegistry(repo),
        EvidenceBasedDecisionProvider(),
        action_registry=ActionRegistry(repo, Decimal("50000")),
    )
    goal = "My product in order ORD-9003 arrived damaged. Please replace it."
    state = controller.run(goal)
    print(f"Final State Status: {state.status}")
    print(f"Customer Case Status: {state.customer_case.status}")
    print(f"Customer Case Goal: {state.customer_case.original_goal}")
    print(f"Requested Resolution: {state.customer_case.requested_resolution}")
    print(f"Final Resolution: {str(state.customer_case.final_resolution).replace('₹', 'INR ')}")
    print("\nActions Executed (Adaptive Pivot):")
    for a in state.actions:
        print(f"  - {a}")
    print("\nVerification Results:")
    for v in state.customer_case.verification_results:
        print(f"  - {str(v).replace('₹', 'INR ')}")
    print()
    return state


def run_test_c():
    print("==================================================================")
    print("REAL MANUAL TEST C: 'I want to cancel my shipped order ORD-9004.' (Policy Restriction)")
    print("==================================================================")
    repo = SimulatedCompanyRepository("customer_refund_denied_policy_escalation")
    controller = AgentController(
        ToolRegistry(repo),
        EvidenceBasedDecisionProvider(),
        action_registry=ActionRegistry(repo, Decimal("50000")),
    )
    goal = "I want to cancel my shipped order ORD-9004."
    state = controller.run(goal)
    print(f"Final State Status: {state.status}")
    print(f"Customer Case Status: {state.customer_case.status}")
    print(f"Customer Case Goal: {state.customer_case.original_goal}")
    print(f"Requested Resolution: {state.customer_case.requested_resolution}")
    print(f"Escalation Reason: {state.customer_case.escalation_reason}")
    print(f"Final Resolution: {state.customer_case.final_resolution}")
    print("\nActions Executed:")
    for a in state.actions:
        print(f"  - {a}")
    print("\nVerification Results:")
    for v in state.customer_case.verification_results:
        print(f"  - {str(v).replace('₹', 'INR ')}")
    print()
    return state


if __name__ == "__main__":
    run_test_a()
    run_test_b()
    run_test_c()
