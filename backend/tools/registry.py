"""Explicit registry for the initial read-only simulated-company tools."""

from typing import Any

from pydantic import ValidationError

from backend.data.database import SimulatedCompanyRepository
from backend.models.tools import ToolCall, ToolMetadata, ToolResult
from backend.tools.analytics import OrderMetricsTool, ProductSalesTool, RevenueMetricsTool
from backend.tools.base import ReadOnlyTool
from backend.tools.inventory import InventoryStatusTool
from backend.tools.payments import PaymentStatusTool
from backend.tools.suppliers import SupplierStatusTool
from backend.tools.technical import RecentDeploymentsTool, ServiceHealthTool, SystemLogsTool


class ToolRegistry:
    """Runs only known tools and converts invalid names into structured results."""

    def __init__(self, repository: SimulatedCompanyRepository) -> None:
        tools: list[ReadOnlyTool] = [
            RevenueMetricsTool(), OrderMetricsTool(), ProductSalesTool(), InventoryStatusTool(),
            SupplierStatusTool(), PaymentStatusTool(), ServiceHealthTool(), RecentDeploymentsTool(),
            SystemLogsTool(),
        ]
        self._repository = repository
        self._tools = {tool.name: tool for tool in tools}

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def discover(self) -> list[ToolMetadata]:
        """Return provider-safe metadata for all tools that may be invoked."""
        return [tool.metadata for tool in self._tools.values()]

    def execute(self, tool_call: ToolCall | dict[str, Any]) -> ToolResult:
        """Validate a model-shaped tool call before any tool receives arguments."""
        try:
            validated_call = (
                tool_call if isinstance(tool_call, ToolCall) else ToolCall.model_validate(tool_call)
            )
        except ValidationError as error:
            return ToolResult.failure(
                "unknown", "malformed_tool_call", error.errors()[0]["msg"]
            )
        return self.run(validated_call.name, validated_call.arguments)

    def run(self, tool_name: str, arguments: dict[str, Any] | None = None) -> ToolResult:
        tool = self._tools.get(tool_name)
        if tool is None:
            return ToolResult.failure("unknown", "unknown_tool", f"Tool '{tool_name}' is not registered.")
        return tool.run(self._repository, arguments)
