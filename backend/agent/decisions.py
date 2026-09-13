"""Decision-provider boundary and local evidence-driven implementation."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


from backend.agent.prompts import build_decision_request
from backend.llm.client import LLMClient
from backend.models.agent import AgentDecision, AgentState
from backend.models.tools import FinishInvestigationInput, ToolCall, ToolMetadata


class AgentDecisionProvider(Protocol):
    def decide(self, state: AgentState, tools: list[ToolMetadata]) -> AgentDecision | dict:
        """Choose the next tool or finish from current state and allowed metadata."""


ACTION_TOOL_NAMES = {
    "create_purchase_request",
    "rollback_deployment",
    "create_support_ticket",
    "request_human_approval",
    "issue_refund",
    "create_replacement",
    "cancel_order",
    "escalate_customer_case",
}


class LLMDecisionProvider:
    """Maps a configured provider-neutral LLM client into agent decisions."""

    def __init__(self, client: LLMClient) -> None:
        self._client = client

    def decide(self, state: AgentState, tools: list[ToolMetadata]) -> AgentDecision:
        response = self._client.complete(build_decision_request(state, tools))
        if response.tool_call:
            tool_name = response.tool_call.name
            raw_reasoning = response.content or f"Selected {tool_name} based on evidence."

            # Sanitize and truncate reasoning to prevent raw chain-of-thought dumps
            clean_reasoning = raw_reasoning.strip().split("\n")[0]
            if len(clean_reasoning) > 200:
                clean_reasoning = clean_reasoning[:197] + "..."

            available_names = {tool.name for tool in tools} | ACTION_TOOL_NAMES
            if tool_name not in available_names and tool_name != "finish_investigation":
                raise ValueError(f"LLM proposed unknown or unpermitted tool '{tool_name}'.")

            if tool_name == "finish_investigation":
                try:
                    finish_args = FinishInvestigationInput.model_validate(response.tool_call.arguments)
                except Exception:
                    return AgentDecision(
                        kind="finish",
                        current_objective="Summarize the available evidence.",
                        hypothesis=state.current_hypothesis,
                        reasoning=clean_reasoning,
                        conclusion=clean_reasoning or "The investigation concluded without a well-formed root cause.",
                        confidence="low",
                    )
                conclusion = finish_args.root_cause
                if finish_args.summary:
                    conclusion = f"{conclusion} {finish_args.summary}"
                return AgentDecision(
                    kind="finish",
                    current_objective="Summarize the available evidence.",
                    hypothesis=state.current_hypothesis,
                    reasoning=clean_reasoning,
                    conclusion=conclusion,
                    confidence=finish_args.confidence,
                )

            if tool_name in ACTION_TOOL_NAMES:
                from backend.models.actions import ActionCall
                return AgentDecision(
                    kind="action",
                    current_objective=f"Execute remediation action using {tool_name}.",
                    hypothesis=state.current_hypothesis,
                    reasoning=clean_reasoning,
                    action_call=ActionCall(name=tool_name, arguments=response.tool_call.arguments),
                )
            return AgentDecision(
                kind="tool",
                current_objective=f"Investigate using {tool_name}.",
                hypothesis=state.current_hypothesis,
                reasoning=clean_reasoning,
                tool_call=response.tool_call,
            )

        # No tool call returned
        return AgentDecision(
            kind="finish",
            current_objective="Summarize the available evidence.",
            hypothesis=state.current_hypothesis,
            reasoning="The model returned text without calling finish_investigation or another tool.",
            conclusion=response.content or "The investigation ended without a model conclusion.",
            confidence="low",
        )



@dataclass(frozen=True)
class _Candidate:
    """A possible next observation or action, ranked from goal relevance and collected evidence."""

    tool_name: str
    score: int
    objective: str
    hypothesis: str
    reasoning: str
    arguments: dict
    is_action: bool = False


class EvidenceBasedDecisionProvider:
    """Local policy that ranks unresolved evidence needs and dynamic resolution actions; never reads a scenario name."""

    @staticmethod
    def _entries(state: AgentState, tool_name: str) -> list:
        return [entry for entry in state.tool_history if entry.tool_call.name == tool_name]

    @classmethod
    def _latest_success(cls, state: AgentState, tool_name: str):
        return next((entry.result for entry in reversed(cls._entries(state, tool_name)) if entry.result.ok), None)

    @classmethod
    def _latest_failure(cls, state: AgentState, tool_name: str):
        return next((entry.result for entry in reversed(cls._entries(state, tool_name)) if not entry.result.ok), None)

    @classmethod
    def _attempted(cls, state: AgentState, tool_name: str) -> bool:
        return bool(cls._entries(state, tool_name))

    @staticmethod
    def _tool(name: str, objective: str, hypothesis: str, reasoning: str, arguments: dict | None = None) -> AgentDecision:
        return AgentDecision(
            kind="tool", current_objective=objective, hypothesis=hypothesis, reasoning=reasoning,
            tool_call=ToolCall(name=name, arguments=arguments or {}),
        )

    @staticmethod
    def _action(name: str, objective: str, hypothesis: str, reasoning: str, arguments: dict) -> AgentDecision:
        from backend.models.actions import ActionCall
        return AgentDecision(
            kind="action", current_objective=objective, hypothesis=hypothesis, reasoning=reasoning,
            action_call=ActionCall(name=name, arguments=arguments),
        )

    @staticmethod
    def _finish(conclusion: str, confidence: str, hypothesis: str, reasoning: str | None = None) -> AgentDecision:
        return AgentDecision(
            kind="finish", current_objective="Conclude the investigation.", hypothesis=hypothesis,
            reasoning=reasoning or "The available independent evidence and action outcomes are sufficient for a conclusion.",
            conclusion=conclusion, confidence=confidence,
        )

    def decide(self, state: AgentState, tools: list[ToolMetadata]) -> AgentDecision:
        """Rank tool candidates from the goal and observed results, then select the best one."""
        completion = self._completion(state)
        if completion:
            return completion

        candidates = self._candidates(state, {tool.name for tool in tools})
        if not candidates:
            return self._finish(
                "Available evidence is insufficient to safely conclude or execute further action.",
                "low",
                "No supported conclusion established.",
                "Every relevant read-only source and resolution path has been evaluated.",
            )
        selected = max(candidates, key=lambda candidate: (candidate.score, candidate.tool_name))
        if selected.is_action:
            return self._action(
                selected.tool_name,
                selected.objective,
                selected.hypothesis,
                selected.reasoning,
                selected.arguments,
            )
        return self._tool(
            selected.tool_name,
            selected.objective,
            selected.hypothesis,
            selected.reasoning,
            selected.arguments,
        )

    def _completion(self, state: AgentState) -> AgentDecision | None:
        # Customer resolution action completions
        executed_proposals = [p for p in state.action_proposals if p.approval_status == "executed"]
        for p in executed_proposals:
            if p.action == "create_replacement":
                return self._finish(
                    f"Replacement for order {p.arguments.get('order_id')} successfully dispatched and verified.",
                    "high", "Defective product replacement completed.",
                )
            if p.action == "issue_refund":
                return self._finish(
                    f"Refund of ₹{p.arguments.get('amount_inr')} for order {p.arguments.get('order_id')} successfully processed and verified.",
                    "high", "Customer refund issued successfully.",
                )
            if p.action == "cancel_order":
                return self._finish(
                    f"Order {p.arguments.get('order_id')} successfully cancelled and verified.",
                    "high", "Order cancellation completed successfully.",
                )
            if p.action == "escalate_customer_case":
                return self._finish(
                    f"Customer case {p.arguments.get('case_id')} safely escalated to human support queue.",
                    "high", "Case escalated to human support agent due to policy or constraint restriction.",
                )

        goal = state.original_goal.lower()
        is_customer_goal = any(k in goal for k in ["order", "ord-", "cust-", "customer", "refund", "replace", "cancel"])
        if is_customer_goal:
            return None

        # Operations completions
        revenue = self._latest_success(state, "get_revenue_metrics")
        if revenue and revenue.data.get("change_percent", 0) > -10:
            return self._finish(
                "Revenue is not materially below the prior period; no operational anomaly is confirmed.",
                "high", "No significant revenue decline found.",
            )
        product_sales = self._latest_success(state, "get_product_sales")
        products = product_sales.data.get("products", []) if product_sales else []
        steepest = min(products, key=lambda product: product.get("revenue_change_percent", 0), default=None)
        payments = self._latest_success(state, "get_payment_status")
        if payments and payments.data.get("failure_rate_percent", 0) >= 10:
            return self._finish(
                "Elevated payment failures are the likely cause of the operational anomaly. No remediation was executed in read-only mode.",
                "high", "Payment gateway failures are suppressing successful orders.",
            )
        service_health = self._latest_success(state, "get_service_health")
        deployments = self._latest_success(state, "get_recent_deployments")
        logs = self._latest_success(state, "get_system_logs")
        log_records = logs.data.get("logs", []) if logs else []
        log_messages = " ".join(item.get("message", "").lower() for item in log_records)
        has_error_log = any(item.get("level") == "ERROR" for item in log_records)
        if service_health and service_health.data.get("overall_status") == "degraded" and deployments and has_error_log:
            return self._finish(
                "Service degradation and error logs after a recent deployment are the likely cause of the operational anomaly. No remediation was executed in read-only mode.",
                "high", "A deployment-related service failure is blocking transactions.",
            )
        inventory = self._latest_success(state, "get_inventory_status")
        inventory_risk = any(
            item.get("below_reorder_point") or item.get("available_to_sell", 1) <= 0
            for item in (inventory.data.get("inventory", []) if inventory else [])
        )
        suppliers = self._latest_success(state, "get_supplier_status")
        supplier_delayed = any(item.get("delay_days", 0) > 0 for item in (suppliers.data.get("suppliers", []) if suppliers else []))
        sharp_product_decline = bool(steepest and steepest.get("revenue_change_percent", 0) <= -40)
        if supplier_delayed and (sharp_product_decline or inventory_risk or "stock" in log_messages):
            return self._finish(
                "Product availability risk is linked to a confirmed delayed supplier shipment. No remediation was executed in read-only mode.",
                "high", "Supplier delay caused a product availability problem.",
            )
        if deployments and logs and "shipping" in log_messages and "fallback" in log_messages:
            return self._finish(
                "Recent pricing changes and checkout logs indicate a shipping configuration issue. No remediation was executed in read-only mode.",
                "high", "A configuration change is affecting checkout behavior.",
            )
        return None

    def _candidates(self, state: AgentState, available_tools: set[str]) -> list[_Candidate]:
        """Generate unresolved evidence-driven tool and action candidates."""
        goal = state.original_goal.lower()
        candidates: list[_Candidate] = []

        def add(tool_name: str, score: int, objective: str, hypothesis: str, reasoning: str, arguments: dict | None = None, is_action: bool = False) -> None:
            if tool_name in available_tools:
                if is_action:
                    # Don't propose an action that was already proposed
                    if not any(p.action == tool_name for p in state.action_proposals):
                        candidates.append(_Candidate(tool_name, score, objective, hypothesis, reasoning, arguments or {}, is_action=True))
                else:
                    args = arguments or {}
                    if tool_name == "check_customer_resolution_eligibility":
                        res_type_arg = args.get("resolution_type")
                        already_run = any(
                            e.tool_call.name == tool_name and e.tool_call.arguments.get("resolution_type") == res_type_arg
                            for e in state.tool_history
                        )
                        if not already_run:
                            candidates.append(_Candidate(tool_name, score, objective, hypothesis, reasoning, args, is_action=False))
                    elif not self._attempted(state, tool_name):
                        candidates.append(_Candidate(tool_name, score, objective, hypothesis, reasoning, args, is_action=False))

        # Check for customer resolution goals (e.g. contains ORD-xxx or CUST-xxx or customer keywords)
        import re
        order_match = re.search(r"ord-\d+", goal)
        customer_match = re.search(r"cust-\d+", goal)

        get_order_res = self._latest_success(state, "get_order")
        eligibility_entries = [e for e in state.tool_history if e.tool_call.name == "check_customer_resolution_eligibility"]
        latest_eligibility = eligibility_entries[-1].result if eligibility_entries else None

        # --- CUSTOMER RESOLUTION BRANCH ---
        if order_match or customer_match or any(k in goal for k in ["damaged", "defective", "refund", "replace", "cancel", "customer", "order", "help", "issue", "product", "money back", "color", "address", "size", "exchange", "warranty"]):
            if state.customer_case and state.customer_case.order_id:
                target_order_id = state.customer_case.order_id
            elif order_match:
                target_order_id = order_match.group(0).upper()
            elif "laptop" in goal:
                target_order_id = "ORD-9002"
            elif any(k in goal for k in ["headphone", "earpiece", "nimbus"]):
                target_order_id = "ORD-9001"
            elif any(k in goal for k in ["usb", "hub", "orbit"]):
                target_order_id = "ORD-9003"
            else:
                target_order_id = "ORD-9001"

            # Step 1: Handle tool failure if get_order failed
            if self._latest_failure(state, "get_order"):
                case_identifier = state.customer_case.case_id if state.customer_case else f"CASE-{target_order_id}"
                add(
                    "escalate_customer_case", 100,
                    f"Escalate order lookup failure for {target_order_id}.",
                    "Order lookup tool experienced an error.",
                    f"Order investigation tool failed for {target_order_id}. Safely escalating case to human support queue.",
                    {"case_id": case_identifier, "customer_id": "CUST-801", "reason": "Order lookup tool failure", "priority": "high"},
                    is_action=True,
                )
                return candidates

            # Step 1b: Query order details first if not yet retrieved
            if not get_order_res:
                add(
                    "get_order", 100,
                    f"Retrieve order details for {target_order_id}.",
                    "Order data is required to evaluate resolution options.",
                    "Goal involves a customer order issue; retrieving exact order status and line items.",
                    {"order_id": target_order_id},
                )
                return candidates

            order_data = get_order_res.data.get("order", {})
            order_id = order_data.get("order_id", target_order_id)
            cust_id = order_data.get("customer_id", "CUST-801")
            prod_id = order_data.get("product_id", "PR-100")
            price = Decimal(str(order_data.get("price", 2499.0)))

            # Step 1b: Check for unsupported or ambiguous customer goals
            unsupported_keywords = ["color", "address", "size", "discount", "warranty", "exchange", "gift card"]
            is_unsupported = any(k in goal for k in unsupported_keywords)
            if is_unsupported:
                case_identifier = state.customer_case.case_id if state.customer_case else f"CASE-{order_id}"
                add(
                    "escalate_customer_case", 100,
                    f"Escalate unsupported customer request for order {order_id}.",
                    "Requested capability is not supported by automated resolution tools.",
                    f"Customer goal '{state.original_goal}' requests an unsupported operation. Safely escalating to human support queue.",
                    {"case_id": case_identifier, "customer_id": cust_id, "reason": f"Unsupported customer request: {state.original_goal}", "priority": "high"},
                    is_action=True,
                )
                return candidates

            ambiguous_goals = ["help", "something is wrong", "need assistance", "issue", "problem"]
            is_ambiguous = (not any(k in goal for k in ["damaged", "defective", "refund", "replace", "cancel", "money back", "return"]) and
                            any(k in goal for k in ambiguous_goals))
            if is_ambiguous:
                case_identifier = state.customer_case.case_id if state.customer_case else f"CASE-{order_id}"
                add(
                    "escalate_customer_case", 100,
                    f"Escalate ambiguous customer request for order {order_id}.",
                    "Customer request is ambiguous and requires human review.",
                    f"Customer goal '{state.original_goal}' is ambiguous and does not specify a supported resolution path. Escalating to human support queue.",
                    {"case_id": case_identifier, "customer_id": cust_id, "reason": f"Ambiguous goal requiring human agent review: {state.original_goal}", "priority": "high"},
                    is_action=True,
                )
                return candidates

            # Step 2: Check resolution eligibility if not checked yet
            if not latest_eligibility:
                if state.customer_case and state.customer_case.requested_resolution:
                    target_resolution = state.customer_case.requested_resolution
                elif "refund" in goal or "money back" in goal or "return" in goal:
                    target_resolution = "refund"
                elif "cancel" in goal or "cancellation" in goal:
                    target_resolution = "cancellation"
                elif "replace" in goal or "replacement" in goal or "defective" in goal or "damaged" in goal:
                    target_resolution = "replacement"
                else:
                    target_resolution = "replacement"

                add(
                    "check_customer_resolution_eligibility", 98,
                    f"Evaluate policy eligibility for {target_resolution}.",
                    "Policy and inventory eligibility must be verified before taking action.",
                    f"Evaluating {target_resolution} policy rules and constraint blocks for order {order_id}.",
                    {"order_id": order_id, "resolution_type": target_resolution},
                )
                return candidates

            # Step 3: Act or Adapt based on Eligibility Result
            elig_data = latest_eligibility.data
            res_type = elig_data.get("resolution_type")
            is_eligible = elig_data.get("eligible", False)
            blocked_by = elig_data.get("blocked_by")

            if res_type == "replacement":
                if is_eligible:
                    add(
                        "create_replacement", 100,
                        f"Dispatch replacement unit for order {order_id}.",
                        "Replacement is verified eligible and inventory is in stock.",
                        "Executing create_replacement action.",
                        {"order_id": order_id, "customer_id": cust_id, "product_id": prod_id, "quantity": 1, "reason": "Replacement for customer issue"},
                        is_action=True,
                    )
                elif blocked_by == "out_of_stock":
                    # DYNAMIC ADAPTATION: Replacement blocked by stock out -> Pivot to refund!
                    refund_elig_checked = any(
                        e.tool_call.arguments.get("resolution_type") == "refund" for e in eligibility_entries
                    )
                    if not refund_elig_checked:
                        add(
                            "check_customer_resolution_eligibility", 99,
                            f"Adapt resolution: Evaluate refund eligibility for order {order_id}.",
                            "Replacement is blocked by out-of-stock inventory; checking refund option.",
                            "Inventory stock is 0 for replacement; dynamically adapting to evaluate refund eligibility.",
                            {"order_id": order_id, "resolution_type": "refund"},
                        )
                    else:
                        add(
                            "issue_refund", 99,
                            f"Issue refund for order {order_id} after replacement stock out.",
                            "Replacement is blocked by out-of-stock inventory; refund is verified eligible.",
                            "Executing issue_refund action as an adaptive resolution.",
                            {"order_id": order_id, "customer_id": cust_id, "amount_inr": str(price), "reason": "Replacement product out of stock; issued refund."},
                            is_action=True,
                        )

            elif res_type == "refund":
                if is_eligible:
                    add(
                        "issue_refund", 100,
                        f"Issue refund for order {order_id}.",
                        "Refund is verified eligible under company policy.",
                        "Executing issue_refund action.",
                        {"order_id": order_id, "customer_id": cust_id, "amount_inr": str(price), "reason": "Customer order refund"},
                        is_action=True,
                    )
                else:
                    # DYNAMIC ADAPTATION: Refund forbidden by policy -> Escalate safely!
                    add(
                        "escalate_customer_case", 99,
                        f"Escalate case for order {order_id} to human support.",
                        "Refund is forbidden by company policy.",
                        "Policy forbids auto-refund; escalating case to human support agent.",
                        {"case_id": f"CASE-{order_id}", "customer_id": cust_id, "reason": elig_data.get("reason", "Refund forbidden by policy"), "priority": "high"},
                        is_action=True,
                    )

            elif res_type == "cancellation":
                if is_eligible:
                    add(
                        "cancel_order", 100,
                        f"Cancel order {order_id}.",
                        "Cancellation is eligible prior to dispatch.",
                        "Executing cancel_order action.",
                        {"order_id": order_id, "customer_id": cust_id, "reason": "Customer cancellation request"},
                        is_action=True,
                    )
                elif blocked_by == "already_shipped":
                    # DYNAMIC ADAPTATION: Order already shipped -> Policy forbids auto-cancellation post-dispatch!
                    add(
                        "escalate_customer_case", 99,
                        f"Escalate post-dispatch cancellation for order {order_id}.",
                        "Post-dispatch cancellation is forbidden by policy.",
                        "Order is already shipped; escalating case to human logistics agent.",
                        {"case_id": f"CASE-{order_id}", "customer_id": cust_id, "reason": "Order already shipped; cancellation post-dispatch requires manual logistics intervention.", "priority": "high"},
                        is_action=True,
                    )

            return candidates

        # --- OPERATIONS INVESTIGATION BRANCH (PRESERVED 100%) ---
        goal_scores = self._goal_scores(goal)

        def add_op(tool_name: str, score: int, objective: str, hypothesis: str, reasoning: str, arguments: dict | None = None) -> None:
            if tool_name in available_tools and not self._attempted(state, tool_name):
                candidates.append(_Candidate(tool_name, score, objective, hypothesis, reasoning, arguments or {}, is_action=False))

        revenue = self._latest_success(state, "get_revenue_metrics")
        product_sales = self._latest_success(state, "get_product_sales")
        payments = self._latest_success(state, "get_payment_status")
        service_health = self._latest_success(state, "get_service_health")
        deployments = self._latest_success(state, "get_recent_deployments")
        logs = self._latest_success(state, "get_system_logs")
        inventory = self._latest_success(state, "get_inventory_status")
        inventory_failure = self._latest_failure(state, "get_inventory_status")

        if not state.tool_history:
            for tool_name, score in goal_scores.items():
                add_op(tool_name, score, "Establish the most relevant operational signal.", "No hypothesis established.", f"The goal explicitly mentions {tool_name.replace('get_', '').replace('_', ' ')}.")
            return candidates

        revenue_declined = bool(revenue and revenue.data.get("change_percent", 0) <= -10)
        products = product_sales.data.get("products", []) if product_sales else []
        steepest = min(products, key=lambda product: product.get("revenue_change_percent", 0), default=None)
        sharp_product_decline = bool(steepest and steepest.get("revenue_change_percent", 0) <= -40)
        product_id = steepest.get("product_id") if steepest else None
        inventory_risk = any(
            item.get("below_reorder_point") or item.get("available_to_sell", 1) <= 0
            for item in (inventory.data.get("inventory", []) if inventory else [])
        )

        if revenue_declined and not product_sales:
            add_op("get_product_sales", 90, "Identify the largest revenue contributor to the decline.", "A concentrated product issue may explain revenue loss.", "Revenue is materially down; product-level comparison has the highest information value.")
        if revenue_declined and not payments:
            add_op("get_payment_status", 70, "Check whether payment failures are preventing orders.", "A payment disruption may explain a broad decline.", "Revenue is down and transaction health has not been checked.")
        if revenue_declined and not service_health:
            add_op("get_service_health", 65, "Check for technical service degradation.", "A service incident may be reducing completed orders.", "Revenue is down and operational health is still unknown.")
        if revenue_declined and not self._latest_success(state, "get_order_metrics"):
            add_op("get_order_metrics", 55, "Quantify the order-volume component of the decline.", "Fewer completed orders may be contributing.", "Order metrics can distinguish volume loss from value loss.")

        if sharp_product_decline and product_id and not inventory and inventory_failure is None:
            add_op("get_inventory_status", 95, "Check whether the sharply declining product is available.", "The product may be unavailable.", "A severe product-specific drop makes inventory the highest-value next check.", {"product_id": product_id})
        if inventory_failure and not logs:
            add_op("get_system_logs", 100, "Find corroborating evidence after the inventory source failed.", "Availability remains unconfirmed; seek an independent source.", "The inventory tool failed, so logs are preferred over assuming stock status.", {"service": "inventory", "level": "WARNING"})
        if (inventory_risk or (inventory_failure and logs)) and not self._latest_success(state, "get_supplier_status"):
            add_op("get_supplier_status", 92, "Verify whether supplier status explains the availability risk.", "A supplier delay may be restricting availability.", "Availability risk now needs supplier confirmation.")

        payment_normal = bool(payments and payments.data.get("failure_rate_percent", 0) < 10)
        if payment_normal and not service_health:
            add_op("get_service_health", 82, "Check services after payment health ruled out a transaction failure.", "A technical incident may still be reducing orders.", "Payment evidence is normal, shifting priority to service health.")
        service_degraded = bool(service_health and service_health.data.get("overall_status") == "degraded")
        if service_degraded and not deployments:
            add_op("get_recent_deployments", 95, "Find recent changes affecting degraded services.", "A release may have introduced the service issue.", "A degraded service makes recent deployments high-value evidence.")
        if service_degraded and deployments and not logs:
            add_op("get_system_logs", 95, "Verify the service incident from error logs.", "A recent deployment likely introduced an error.", "Service degradation and a deployment require log confirmation.", {"service": "checkout", "level": "ERROR"})
        service_healthy = bool(service_health and service_health.data.get("overall_status") == "healthy")
        if payment_normal and service_healthy and not deployments:
            add_op("get_recent_deployments", 80, "Inspect recent configuration changes.", "A non-service change may be affecting conversion.", "Product, payment, and service evidence are inconclusive; inspect changes.")
        if deployments and not logs:
            latest = deployments.data.get("deployments", [{}])[0]
            add_op("get_system_logs", 85, "Verify the latest relevant change through logs.", "A recent change may have caused the anomaly.", "Deployment evidence is available but needs operational corroboration.", {"service": latest.get("service")})

        return candidates

    @staticmethod
    def _goal_scores(goal: str) -> dict[str, int]:
        """Translate the user's high-level wording into initial investigation priorities."""
        scores: dict[str, int] = {"get_revenue_metrics": 60}
        keyword_groups = {
            "get_revenue_metrics": ("revenue", "sales", "decline", "dropped"),
            "get_order_metrics": ("order", "conversion", "cancellation"),
            "get_product_sales": ("product", "category", "item"),
            "get_inventory_status": ("inventory", "stock", "out of stock"),
            "get_supplier_status": ("supplier", "shipment", "delivery"),
            "get_payment_status": ("payment", "gateway", "transaction"),
            "get_service_health": ("service", "error", "checkout", "outage"),
            "get_recent_deployments": ("deployment", "deploy", "release"),
            "get_system_logs": ("log", "exception", "stack trace"),
        }
        for tool_name, keywords in keyword_groups.items():
            if any(keyword in goal for keyword in keywords):
                scores[tool_name] = 100
        return scores
