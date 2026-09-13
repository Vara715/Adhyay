from decimal import Decimal
from backend.agent.controller import AgentController
from backend.agent.decisions import EvidenceBasedDecisionProvider
from backend.data.database import SimulatedCompanyRepository
from backend.tools.actions import ActionRegistry
from backend.tools.registry import ToolRegistry

repo = SimulatedCompanyRepository("inventory_supplier_failure")
tool_reg = ToolRegistry(repo)
action_reg = ActionRegistry(repo, Decimal("5000"))
decision_provider = EvidenceBasedDecisionProvider()
controller = AgentController(tool_reg, decision_provider, action_registry=action_reg)

goal = "Customer CUST-801 requested refund for damaged order ORD-9002."
state = controller.run(goal)

print(f"STATUS: {state.status}")
print("EVENTS:")
for e in state.events:
    print(f"  {e.event_type}: {e.summary}")
print("ACTION PROPOSALS:")
for p in state.action_proposals:
    print(f"  {p.action} (permission: {p.permission_level}, status: {p.approval_status})")
