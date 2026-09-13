"""Read-only scoped log search tool for customer case investigation."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

from backend.data.database import SimulatedCompanyRepository
from backend.models.tools import ToolResult
from backend.tools.base import ReadOnlyTool


class SearchCaseLogsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str | None = Field(default=None, description="Order ID filter (e.g. ORD-9001)")
    customer_id: str | None = Field(default=None, description="Customer ID filter (e.g. CUST-801)")
    log_type: Literal["warehouse_packing", "shipping_scan", "payment_gateway", "all"] = Field(
        default="all", description="Log category to search"
    )
    query: str | None = Field(default=None, description="Optional text filter")


class SearchCaseLogsTool(ReadOnlyTool[SearchCaseLogsInput]):
    name = "search_case_logs"
    description = "Search read-only operational logs (warehouse barcode packing scans, courier transit logs, payment gateway traces) scoped to a customer case."
    input_model = SearchCaseLogsInput

    def execute(self, repository: SimulatedCompanyRepository, arguments: SearchCaseLogsInput) -> ToolResult:
        logs = repository.get_collection("logs") if "logs" in repository._data else []
        case_logs = repository.get_collection("case_logs") if "case_logs" in repository._data else []
        all_logs = list(logs) + list(case_logs)

        filtered = []
        for entry in all_logs:
            if arguments.order_id and entry.get("order_id") and entry.get("order_id") != arguments.order_id:
                continue
            if arguments.customer_id and entry.get("customer_id") and entry.get("customer_id") != arguments.customer_id:
                continue
            if arguments.log_type != "all" and entry.get("log_type") and entry.get("log_type") != arguments.log_type:
                continue
            if arguments.query and arguments.query.lower() not in str(entry).lower():
                continue
            # Security filter: Never leak credentials or secrets
            clean_entry = {k: v for k, v in entry.items() if "secret" not in k and "token" not in k and "key" not in k}
            filtered.append(clean_entry)

        # Cap results to prevent response bloating
        filtered = filtered[:10]

        return ToolResult.success(
            self.name,
            f"Found {len(filtered)} operational log entry/entries for investigation.",
            {
                "order_id": arguments.order_id,
                "customer_id": arguments.customer_id,
                "log_type": arguments.log_type,
                "log_count": len(filtered),
                "logs": filtered,
            },
        )
