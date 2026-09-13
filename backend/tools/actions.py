"""Minimal simulated action registry with controller-enforced permissions."""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.data.database import SimulatedCompanyRepository
from backend.models.actions import ActionProposal, PermissionLevel, VerificationOutcome
from backend.models.tools import ToolMetadata, ToolResult


class PurchaseRequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_id: str = Field(min_length=1)
    product_id: str = Field(min_length=1)
    quantity: int = Field(ge=1, le=10_000)
    unit_cost_inr: Decimal = Field(gt=0)


class RollbackDeploymentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deployment_id: str = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=500)


class SupportTicketInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=1, max_length=1_000)
    severity: str = Field(default="medium", pattern="^(low|medium|high)$")


class ApprovalRequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str = Field(min_length=1)


class ActionTool(ABC):
    name: str
    description: str
    input_model: type[BaseModel]

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(name=self.name, description=self.description, input_schema=self.input_model.model_json_schema())

    def validate(self, arguments: dict[str, Any]) -> BaseModel | ToolResult:
        try:
            return self.input_model.model_validate(arguments)
        except ValidationError as error:
            return ToolResult.failure(self.name, "invalid_input", error.errors()[0]["msg"])

    @abstractmethod
    def permission_level(self, arguments: BaseModel, approval_threshold_inr: Decimal) -> PermissionLevel:
        """Determine permission from validated, structured arguments."""

    @abstractmethod
    def estimated_impact(self, arguments: BaseModel) -> dict[str, Any]:
        """Describe expected impact without making the change."""

    @abstractmethod
    def risk(self, arguments: BaseModel) -> str:
        """Return a concise user-facing risk description."""

    @abstractmethod
    def capture_baseline(self, repository: SimulatedCompanyRepository, arguments: BaseModel) -> dict[str, Any]:
        """Query the relevant system for the expected state change, before the action runs."""

    @abstractmethod
    def verify(self, repository: SimulatedCompanyRepository, arguments: BaseModel, baseline: dict[str, Any]) -> VerificationOutcome:
        """Query the relevant system again after the action runs and compare against the baseline."""


class CreatePurchaseRequestTool(ActionTool):
    name = "create_purchase_request"
    description = "Create a simulated procurement request for replenishment."
    input_model = PurchaseRequestInput

    def permission_level(self, arguments: PurchaseRequestInput, approval_threshold_inr: Decimal) -> PermissionLevel:
        return "high_risk" if arguments.quantity * arguments.unit_cost_inr >= approval_threshold_inr else "low_risk"

    def estimated_impact(self, arguments: PurchaseRequestInput) -> dict[str, Any]:
        return {"estimated_cost_inr": str(arguments.quantity * arguments.unit_cost_inr), "units": arguments.quantity}

    def risk(self, arguments: PurchaseRequestInput) -> str:
        return "Procurement commitment affects inventory spend."

    def capture_baseline(self, repository: SimulatedCompanyRepository, arguments: PurchaseRequestInput) -> dict[str, Any]:
        inventory = repository.get_collection("inventory")
        record = next((item for item in inventory if item.get("product_id") == arguments.product_id), {})
        return {"product_id": arguments.product_id, "on_hand": record.get("on_hand")}

    def verify(self, repository: SimulatedCompanyRepository, arguments: PurchaseRequestInput, baseline: dict[str, Any]) -> VerificationOutcome:
        requests = repository.get_collection("purchase_requests")
        matching = [
            item for item in requests
            if item.get("product_id") == arguments.product_id and item.get("supplier_id") == arguments.supplier_id
        ]
        if not matching:
            return VerificationOutcome(
                status="failed", detail="No purchase request record was found after submission.",
                before=baseline, after={},
            )
        latest = matching[-1]
        after = {"product_id": arguments.product_id, "request_status": latest.get("status")}
        if latest.get("status") == "submitted":
            return VerificationOutcome(
                status="inconclusive",
                detail="Purchase request was submitted, but supplier fulfillment has not yet been confirmed.",
                before=baseline, after=after,
            )
        return VerificationOutcome(status="verified", detail="Purchase request is confirmed.", before=baseline, after=after)


class RollbackDeploymentTool(ActionTool):
    name = "rollback_deployment"
    description = "Roll back a simulated production deployment."
    input_model = RollbackDeploymentInput

    def permission_level(self, arguments: RollbackDeploymentInput, approval_threshold_inr: Decimal) -> PermissionLevel:
        return "high_risk"

    def estimated_impact(self, arguments: RollbackDeploymentInput) -> dict[str, Any]:
        return {"deployment_id": arguments.deployment_id, "expected_effect": "Restore the previous deployment version."}

    def risk(self, arguments: RollbackDeploymentInput) -> str:
        return "Production rollback can affect active checkout traffic."

    def capture_baseline(self, repository: SimulatedCompanyRepository, arguments: RollbackDeploymentInput) -> dict[str, Any]:
        deployments = repository.get_collection("deployments")
        deployment = next((item for item in deployments if item.get("deployment_id") == arguments.deployment_id), None)
        service = deployment.get("service") if deployment else None
        service_health = repository.get_collection("service_health")
        health = service_health.get(service, {}) if service else {}
        return {
            "deployment_id": arguments.deployment_id,
            "service": service,
            "status": health.get("status"),
            "error_rate_percent": health.get("error_rate_percent"),
        }

    def verify(self, repository: SimulatedCompanyRepository, arguments: RollbackDeploymentInput, baseline: dict[str, Any]) -> VerificationOutcome:
        deployments = repository.get_collection("deployments")
        deployment = next((item for item in deployments if item.get("deployment_id") == arguments.deployment_id), None)
        if deployment is None or deployment.get("status") != "rolled_back":
            return VerificationOutcome(
                status="failed",
                detail=f"Deployment {arguments.deployment_id} could not be confirmed as rolled back.",
                before=baseline, after={},
            )
        service = deployment.get("service")
        service_health = repository.get_collection("service_health")
        health = service_health.get(service, {}) if service else {}
        after = {
            "deployment_id": arguments.deployment_id,
            "service": service,
            "status": health.get("status"),
            "error_rate_percent": health.get("error_rate_percent"),
        }
        if health.get("status") == "healthy":
            return VerificationOutcome(
                status="verified", detail=f"{service} service health returned to healthy after the rollback.",
                before=baseline, after=after,
            )
        return VerificationOutcome(
            status="failed",
            detail=f"{service} service health is still {health.get('status')} after the rollback; the deployment may not be the root cause.",
            before=baseline, after=after,
        )


class CreateSupportTicketTool(ActionTool):
    name = "create_support_ticket"
    description = "Create a simulated internal support escalation ticket."
    input_model = SupportTicketInput

    def permission_level(self, arguments: SupportTicketInput, approval_threshold_inr: Decimal) -> PermissionLevel:
        return "low_risk"

    def estimated_impact(self, arguments: SupportTicketInput) -> dict[str, Any]:
        return {"expected_effect": "Creates an internal escalation ticket.", "severity": arguments.severity}

    def risk(self, arguments: SupportTicketInput) -> str:
        return "Creates an internal record but does not change production state."

    def capture_baseline(self, repository: SimulatedCompanyRepository, arguments: SupportTicketInput) -> dict[str, Any]:
        tickets = repository.get_collection("support_tickets")
        return {"open_ticket_count": sum(1 for ticket in tickets if ticket.get("status") == "open")}

    def verify(self, repository: SimulatedCompanyRepository, arguments: SupportTicketInput, baseline: dict[str, Any]) -> VerificationOutcome:
        tickets = repository.get_collection("support_tickets")
        matching = [
            ticket for ticket in tickets
            if ticket.get("title") == arguments.title and ticket.get("category") == "agent_escalation"
        ]
        if not matching:
            return VerificationOutcome(
                status="failed", detail="No escalation ticket was found after creation.", before=baseline, after={},
            )
        latest = matching[-1]
        after = {"ticket_id": latest.get("ticket_id"), "status": latest.get("status")}
        if latest.get("status") == "open":
            return VerificationOutcome(
                status="verified", detail="Escalation ticket was created and is open.", before=baseline, after=after,
            )
        return VerificationOutcome(
            status="inconclusive", detail="Escalation ticket exists but is not open.", before=baseline, after=after,
        )


class RequestHumanApprovalTool(ActionTool):
    name = "request_human_approval"
    description = "Create a simulated human approval request for a high-risk action."
    input_model = ApprovalRequestInput

    def permission_level(self, arguments: ApprovalRequestInput, approval_threshold_inr: Decimal) -> PermissionLevel:
        return "read_only"

    def estimated_impact(self, arguments: ApprovalRequestInput) -> dict[str, Any]:
        return {"action_id": arguments.action_id, "expected_effect": "Pauses pending human approval."}

    def risk(self, arguments: ApprovalRequestInput) -> str:
        return "No operational change is made."

    def capture_baseline(self, repository: SimulatedCompanyRepository, arguments: ApprovalRequestInput) -> dict[str, Any]:
        return {}

    def verify(self, repository: SimulatedCompanyRepository, arguments: ApprovalRequestInput, baseline: dict[str, Any]) -> VerificationOutcome:
        return VerificationOutcome(status="verified", detail="No operational state change to verify.", before={}, after={})


class IssueRefundInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    amount_inr: Decimal = Field(gt=0)
    reason: str = Field(min_length=1, max_length=500)


class CreateReplacementInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    product_id: str = Field(min_length=1)
    quantity: int = Field(ge=1, le=100)
    reason: str = Field(min_length=1, max_length=500)


class CancelOrderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=500)


class EscalateCustomerCaseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=500)
    priority: str = Field(default="medium", pattern="^(low|medium|high|urgent)$")


class IssueRefundTool(ActionTool):
    name = "issue_refund"
    description = "Issue a financial refund for a customer order."
    input_model = IssueRefundInput

    def permission_level(self, arguments: IssueRefundInput, approval_threshold_inr: Decimal) -> PermissionLevel:
        return "high_risk" if arguments.amount_inr >= approval_threshold_inr else "low_risk"

    def estimated_impact(self, arguments: IssueRefundInput) -> dict[str, Any]:
        return {"order_id": arguments.order_id, "amount_inr": str(arguments.amount_inr), "expected_effect": "Process financial refund to customer."}

    def risk(self, arguments: IssueRefundInput) -> str:
        return "Financial refund permanently credits the customer's account."

    def capture_baseline(self, repository: SimulatedCompanyRepository, arguments: IssueRefundInput) -> dict[str, Any]:
        order = repository.get_order(arguments.order_id) or {}
        return {"order_id": arguments.order_id, "status": order.get("status"), "refund_state": order.get("refund_state")}

    def verify(self, repository: SimulatedCompanyRepository, arguments: IssueRefundInput, baseline: dict[str, Any]) -> VerificationOutcome:
        order = repository.get_order(arguments.order_id) or {}
        refunds = repository.get_collection("refunds")
        refund_record = next((r for r in refunds if r.get("order_id") == arguments.order_id), None)
        after = {"order_id": arguments.order_id, "status": order.get("status"), "refund_state": order.get("refund_state")}

        if order.get("status") == "refunded" and order.get("refund_state") == "completed" and refund_record is not None:
            return VerificationOutcome(
                status="verified",
                detail=f"Refund of ₹{arguments.amount_inr} for order {arguments.order_id} verified.",
                before=baseline, after=after,
            )
        return VerificationOutcome(
            status="failed",
            detail=f"Order {arguments.order_id} status was not updated to refunded (current status: {order.get('status')}).",
            before=baseline, after=after,
        )


class CreateReplacementTool(ActionTool):
    name = "create_replacement"
    description = "Process an order replacement and dispatch replacement inventory."
    input_model = CreateReplacementInput

    def permission_level(self, arguments: CreateReplacementInput, approval_threshold_inr: Decimal) -> PermissionLevel:
        return "low_risk"

    def estimated_impact(self, arguments: CreateReplacementInput) -> dict[str, Any]:
        return {"order_id": arguments.order_id, "product_id": arguments.product_id, "quantity": arguments.quantity, "expected_effect": "Deduct inventory and dispatch replacement unit."}

    def risk(self, arguments: CreateReplacementInput) -> str:
        return "Dispatches replacement unit and updates inventory stock."

    def capture_baseline(self, repository: SimulatedCompanyRepository, arguments: CreateReplacementInput) -> dict[str, Any]:
        order = repository.get_order(arguments.order_id) or {}
        inv = repository.get_collection("inventory")
        record = next((item for item in inv if item.get("product_id") == arguments.product_id), {})
        return {
            "order_id": arguments.order_id,
            "product_id": arguments.product_id,
            "on_hand": record.get("on_hand"),
            "replacement_state": order.get("replacement_state"),
        }

    def verify(self, repository: SimulatedCompanyRepository, arguments: CreateReplacementInput, baseline: dict[str, Any]) -> VerificationOutcome:
        order = repository.get_order(arguments.order_id) or {}
        inv = repository.get_collection("inventory")
        record = next((item for item in inv if item.get("product_id") == arguments.product_id), {})
        replacements = repository.get_collection("replacements")
        replacement_record = next((r for r in replacements if r.get("order_id") == arguments.order_id), None)

        after = {
            "order_id": arguments.order_id,
            "product_id": arguments.product_id,
            "on_hand": record.get("on_hand"),
            "replacement_state": order.get("replacement_state"),
        }

        if order.get("replacement_state") == "completed" and replacement_record is not None:
            return VerificationOutcome(
                status="verified",
                detail=f"Replacement unit for product {arguments.product_id} (order {arguments.order_id}) verified.",
                before=baseline, after=after,
            )
        return VerificationOutcome(
            status="failed",
            detail=f"Order {arguments.order_id} replacement state could not be verified.",
            before=baseline, after=after,
        )


class CancelOrderTool(ActionTool):
    name = "cancel_order"
    description = "Cancel a pending customer order and stop fulfillment."
    input_model = CancelOrderInput

    def permission_level(self, arguments: CancelOrderInput, approval_threshold_inr: Decimal) -> PermissionLevel:
        return "low_risk"

    def estimated_impact(self, arguments: CancelOrderInput) -> dict[str, Any]:
        return {"order_id": arguments.order_id, "expected_effect": "Cancel order and halt shipment."}

    def risk(self, arguments: CancelOrderInput) -> str:
        return "Order cancellation updates fulfillment status to unfulfilled and cancels order."

    def capture_baseline(self, repository: SimulatedCompanyRepository, arguments: CancelOrderInput) -> dict[str, Any]:
        order = repository.get_order(arguments.order_id) or {}
        return {"order_id": arguments.order_id, "status": order.get("status"), "cancellation_state": order.get("cancellation_state")}

    def verify(self, repository: SimulatedCompanyRepository, arguments: CancelOrderInput, baseline: dict[str, Any]) -> VerificationOutcome:
        order = repository.get_order(arguments.order_id) or {}
        after = {"order_id": arguments.order_id, "status": order.get("status"), "cancellation_state": order.get("cancellation_state")}

        if order.get("status") == "cancelled" and order.get("cancellation_state") == "completed":
            return VerificationOutcome(
                status="verified",
                detail=f"Order {arguments.order_id} cancellation verified.",
                before=baseline, after=after,
            )
        return VerificationOutcome(
            status="failed",
            detail=f"Order {arguments.order_id} status was not updated to cancelled (current status: {order.get('status')}).",
            before=baseline, after=after,
        )


class EscalateCustomerCaseTool(ActionTool):
    name = "escalate_customer_case"
    description = "Escalate an unresolved customer case to a human support agent."
    input_model = EscalateCustomerCaseInput

    def permission_level(self, arguments: EscalateCustomerCaseInput, approval_threshold_inr: Decimal) -> PermissionLevel:
        return "low_risk"

    def estimated_impact(self, arguments: EscalateCustomerCaseInput) -> dict[str, Any]:
        return {"case_id": arguments.case_id, "customer_id": arguments.customer_id, "priority": arguments.priority, "expected_effect": "Creates a human escalation record in customer support queue."}

    def risk(self, arguments: EscalateCustomerCaseInput) -> str:
        return "Routes customer case to human support agent."

    def capture_baseline(self, repository: SimulatedCompanyRepository, arguments: EscalateCustomerCaseInput) -> dict[str, Any]:
        tickets = repository.get_collection("support_tickets")
        return {"open_customer_escalations": sum(1 for t in tickets if t.get("category") == "customer_escalation")}

    def verify(self, repository: SimulatedCompanyRepository, arguments: EscalateCustomerCaseInput, baseline: dict[str, Any]) -> VerificationOutcome:
        tickets = repository.get_collection("support_tickets")
        matching = [t for t in tickets if t.get("category") == "customer_escalation" and t.get("customer_id") == arguments.customer_id]
        if not matching:
            return VerificationOutcome(
                status="failed", detail=f"No customer escalation ticket was found for case {arguments.case_id}.",
                before=baseline, after={},
            )
        latest = matching[-1]
        after = {"ticket_id": latest.get("ticket_id"), "status": latest.get("status")}
        return VerificationOutcome(
            status="verified",
            detail=f"Customer case {arguments.case_id} successfully escalated to human agent queue (ticket {latest.get('ticket_id')}).",
            before=baseline, after=after,
        )


class ActionRegistry:
    """Validates, proposes, approves, rejects, and executes simulated actions safely."""

    def __init__(self, repository: SimulatedCompanyRepository, approval_threshold_inr: Decimal) -> None:
        self._repository = repository
        self._approval_threshold_inr = approval_threshold_inr
        tools: list[ActionTool] = [
            CreatePurchaseRequestTool(), RollbackDeploymentTool(), CreateSupportTicketTool(), RequestHumanApprovalTool(),
            IssueRefundTool(), CreateReplacementTool(), CancelOrderTool(), EscalateCustomerCaseTool(),
        ]
        self._tools = {tool.name: tool for tool in tools}


    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def discover(self) -> list[ToolMetadata]:
        return [tool.metadata for tool in self._tools.values()]

    def propose(self, action_name: str, arguments: dict[str, Any], *, reason: str, evidence: list[str]) -> ActionProposal | ToolResult:
        tool = self._tools.get(action_name)
        if tool is None:
            return ToolResult.failure("unknown", "unknown_tool", f"Action '{action_name}' is not registered.")
        validated = tool.validate(arguments)
        if isinstance(validated, ToolResult):
            return validated
        permission = tool.permission_level(validated, self._approval_threshold_inr)
        return ActionProposal(
            action=action_name, arguments=validated.model_dump(mode="json"), reason=reason, evidence=evidence,
            estimated_impact=tool.estimated_impact(validated), risk=tool.risk(validated), permission_level=permission,
            approval_status="pending" if permission == "high_risk" else "not_required",
        )

    def request_human_approval(self, proposal: ActionProposal) -> ToolResult:
        if proposal.permission_level != "high_risk":
            return ToolResult.failure("request_human_approval", "approval_not_required", "This action does not require approval.")
        proposal.approval_status = "pending"
        return ToolResult.success("request_human_approval", "Human approval is required before this action can run.", {"action_id": proposal.action_id})

    @staticmethod
    def approve(proposal: ActionProposal) -> ToolResult:
        if proposal.approval_status != "pending":
            return ToolResult.failure("request_human_approval", "invalid_approval_state", "Only pending actions can be approved.")
        proposal.approval_status = "approved"
        return ToolResult.success("request_human_approval", "Approval recorded.", {"action_id": proposal.action_id})

    @staticmethod
    def reject(proposal: ActionProposal) -> ToolResult:
        if proposal.approval_status != "pending":
            return ToolResult.failure("request_human_approval", "invalid_approval_state", "Only pending actions can be rejected.")
        proposal.approval_status = "rejected"
        return ToolResult.success("request_human_approval", "Rejection recorded.", {"action_id": proposal.action_id})

    def capture_baseline(self, proposal: ActionProposal) -> dict[str, Any]:
        """Query the relevant system for the expected state change, before executing."""
        tool = self._tools[proposal.action]
        validated = tool.input_model.model_validate(proposal.arguments)
        return tool.capture_baseline(self._repository, validated)

    def verify(self, proposal: ActionProposal, baseline: dict[str, Any]) -> VerificationOutcome:
        """Query the relevant system again and compare against the pre-action baseline."""
        tool = self._tools[proposal.action]
        validated = tool.input_model.model_validate(proposal.arguments)
        return tool.verify(self._repository, validated, baseline)

    def execute(self, proposal: ActionProposal) -> ToolResult:
        if proposal.approval_status == "rejected":
            return ToolResult.failure(proposal.action, "invalid_action_state", "Action was rejected by human reviewer and cannot execute.")
        if proposal.permission_level == "high_risk" and proposal.approval_status != "approved":
            return ToolResult.failure(proposal.action, "approval_required", "High-risk action cannot execute without explicit approval.")
        if proposal.approval_status in {"failed", "executed"}:
            return ToolResult.failure(proposal.action, "invalid_action_state", "Action is not executable in its current approval state.")

        failure = self._repository.get_action_failure(proposal.action)
        if failure:
            proposal.approval_status = "failed"
            proposal.outcome_summary = failure.message
            return ToolResult.failure(proposal.action, failure.code, failure.message)
        self._repository.record_action({"action_id": proposal.action_id, "action": proposal.action, "arguments": proposal.arguments})
        self._repository.apply_action_effect(proposal.action, proposal.arguments, proposal.action_id)
        proposal.approval_status = "executed"
        proposal.outcome_summary = "Simulated action executed; verification has not run."
        return ToolResult.success(proposal.action, proposal.outcome_summary, {"action_id": proposal.action_id})
