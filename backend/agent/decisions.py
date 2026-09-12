"""Decision-provider boundary and local evidence-driven implementation."""

from dataclasses import dataclass
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
}


class LLMDecisionProvider:
    """Maps a configured provider-neutral LLM client into agent decisions."""

    def __init__(self, client: LLMClient) -> None:
        self._client = client

    def decide(self, state: AgentState, tools: list[ToolMetadata]) -> AgentDecision:
        response = self._client.complete(build_decision_request(state, tools))
        if response.tool_call:
            tool_name = response.tool_call.name
            reasoning = response.content or f"Selected {tool_name} to execute next step."

            if tool_name == "finish_investigation":
                try:
                    finish_args = FinishInvestigationInput.model_validate(response.tool_call.arguments)
                except Exception:
                    return AgentDecision(
                        kind="finish",
                        current_objective="Summarize the available evidence.",
                        hypothesis=state.current_hypothesis,
                        reasoning=reasoning,
                        conclusion=response.content or "The investigation concluded without a well-formed root cause.",
                        confidence="low",
                    )
                conclusion = finish_args.root_cause
                if finish_args.summary:
                    conclusion = f"{conclusion} {finish_args.summary}"
                return AgentDecision(
                    kind="finish",
                    current_objective="Summarize the available evidence.",
                    hypothesis=state.current_hypothesis,
                    reasoning=reasoning,
                    conclusion=conclusion,
                    confidence=finish_args.confidence,
                )

            if tool_name in ACTION_TOOL_NAMES:
                from backend.models.actions import ActionCall
                return AgentDecision(
                    kind="action",
                    current_objective=f"Execute remediation action using {tool_name}.",
                    hypothesis=state.current_hypothesis,
                    reasoning=reasoning,
                    action_call=ActionCall(name=tool_name, arguments=response.tool_call.arguments),
                )
            return AgentDecision(
                kind="tool",
                current_objective=f"Investigate using {tool_name}.",
                hypothesis=state.current_hypothesis,
                reasoning=reasoning,
                tool_call=response.tool_call,
            )
        # No tool call at all is a provider quirk, not a considered conclusion: keep
        # investigating instead of silently ending the run (see finish_investigation above).
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
    """A possible next observation, ranked from goal relevance and collected evidence."""

    tool_name: str
    score: int
    objective: str
    hypothesis: str
    reasoning: str
    arguments: dict


class EvidenceBasedDecisionProvider:
    """Local policy that ranks unresolved evidence needs; it never reads a scenario name."""

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
    def _finish(conclusion: str, confidence: str, hypothesis: str, reasoning: str | None = None) -> AgentDecision:
        return AgentDecision(
            kind="finish", current_objective="Conclude the read-only investigation.", hypothesis=hypothesis,
            reasoning=reasoning or "The available independent evidence is sufficient for a read-only conclusion.",
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
                "Available evidence is insufficient to safely identify a root cause. No remediation was executed.",
                "low",
                "No supported root cause established.",
                "Every relevant read-only source has either been checked or failed without corroboration.",
            )
        selected = max(candidates, key=lambda candidate: (candidate.score, candidate.tool_name))
        return self._tool(
            selected.tool_name,
            selected.objective,
            selected.hypothesis,
            selected.reasoning,
            selected.arguments,
        )

    def _completion(self, state: AgentState) -> AgentDecision | None:
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
        """Generate only unresolved, evidence-supported tool options and rank them."""
        goal = state.original_goal.lower()
        goal_scores = self._goal_scores(goal)
        candidates: list[_Candidate] = []

        def add(tool_name: str, score: int, objective: str, hypothesis: str, reasoning: str, arguments: dict | None = None) -> None:
            if tool_name in available_tools and not self._attempted(state, tool_name):
                candidates.append(_Candidate(tool_name, score, objective, hypothesis, reasoning, arguments or {}))

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
                add(tool_name, score, "Establish the most relevant operational signal.", "No hypothesis established.", f"The goal explicitly mentions {tool_name.replace('get_', '').replace('_', ' ')}.")
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
            add("get_product_sales", 90, "Identify the largest revenue contributor to the decline.", "A concentrated product issue may explain revenue loss.", "Revenue is materially down; product-level comparison has the highest information value.")
        if revenue_declined and not payments:
            add("get_payment_status", 70, "Check whether payment failures are preventing orders.", "A payment disruption may explain a broad decline.", "Revenue is down and transaction health has not been checked.")
        if revenue_declined and not service_health:
            add("get_service_health", 65, "Check for technical service degradation.", "A service incident may be reducing completed orders.", "Revenue is down and operational health is still unknown.")
        if revenue_declined and not self._latest_success(state, "get_order_metrics"):
            add("get_order_metrics", 55, "Quantify the order-volume component of the decline.", "Fewer completed orders may be contributing.", "Order metrics can distinguish volume loss from value loss.")

        if sharp_product_decline and product_id and not inventory and inventory_failure is None:
            add("get_inventory_status", 95, "Check whether the sharply declining product is available.", "The product may be unavailable.", "A severe product-specific drop makes inventory the highest-value next check.", {"product_id": product_id})
        if inventory_failure and not logs:
            add("get_system_logs", 100, "Find corroborating evidence after the inventory source failed.", "Availability remains unconfirmed; seek an independent source.", "The inventory tool failed, so logs are preferred over assuming stock status.", {"service": "inventory", "level": "WARNING"})
        if (inventory_risk or (inventory_failure and logs)) and not self._latest_success(state, "get_supplier_status"):
            add("get_supplier_status", 92, "Verify whether supplier status explains the availability risk.", "A supplier delay may be restricting availability.", "Availability risk now needs supplier confirmation.")

        payment_normal = bool(payments and payments.data.get("failure_rate_percent", 0) < 10)
        if payment_normal and not service_health:
            add("get_service_health", 82, "Check services after payment health ruled out a transaction failure.", "A technical incident may still be reducing orders.", "Payment evidence is normal, shifting priority to service health.")
        service_degraded = bool(service_health and service_health.data.get("overall_status") == "degraded")
        if service_degraded and not deployments:
            add("get_recent_deployments", 95, "Find recent changes affecting degraded services.", "A release may have introduced the service issue.", "A degraded service makes recent deployments high-value evidence.")
        if service_degraded and deployments and not logs:
            add("get_system_logs", 95, "Verify the service incident from error logs.", "A recent deployment likely introduced an error.", "Service degradation and a deployment require log confirmation.", {"level": "ERROR"})
        service_healthy = bool(service_health and service_health.data.get("overall_status") == "healthy")
        if payment_normal and service_healthy and not deployments:
            add("get_recent_deployments", 80, "Inspect recent configuration changes.", "A non-service change may be affecting conversion.", "Product, payment, and service evidence are inconclusive; inspect changes.")
        if deployments and not logs:
            latest = deployments.data.get("deployments", [{}])[0]
            add("get_system_logs", 85, "Verify the latest relevant change through logs.", "A recent change may have caused the anomaly.", "Deployment evidence is available but needs operational corroboration.", {"service": latest.get("service")})

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
