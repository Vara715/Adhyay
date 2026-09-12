"""Shared, serializable schemas for deterministic tool execution."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ToolError(BaseModel):
    """A safe, structured failure returned by a tool instead of an exception."""

    code: str
    message: str
    retryable: bool = False


class ToolWarning(BaseModel):
    """A non-fatal data-quality condition that should influence later decisions."""

    code: Literal["incomplete_data", "contradictory_evidence", "stale_data"]
    message: str


class ToolResult(BaseModel):
    """The normalized result shape used by every read-only tool."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    ok: bool
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)
    error: ToolError | None = None
    warnings: list[ToolWarning] = Field(default_factory=list)

    @classmethod
    def success(cls, tool_name: str, summary: str, data: dict[str, Any]) -> "ToolResult":
        return cls(tool_name=tool_name, ok=True, summary=summary, data=data)

    @classmethod
    def failure(
        cls, tool_name: str, code: str, message: str, *, retryable: bool = False
    ) -> "ToolResult":
        return cls(
            tool_name=tool_name,
            ok=False,
            summary=message,
            error=ToolError(code=code, message=message, retryable=retryable),
        )


class ToolMetadata(BaseModel):
    """Safe tool discovery data supplied to a future model provider."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    input_schema: dict[str, Any]


class ToolCall(BaseModel):
    """A provider-neutral request to invoke one registered tool."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProductSalesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str | None = None
    category: str | None = None


class InventoryStatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str | None = None


class SupplierStatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_id: str | None = None


class RecentDeploymentsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=5, ge=1, le=10)


class SystemLogsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service: str | None = None
    level: Literal["INFO", "WARNING", "ERROR"] | None = None
    limit: int = Field(default=20, ge=1, le=50)


class FinishInvestigationInput(BaseModel):
    """The only structured way an LLM-driven run may reach a completed/failed status.

    Ending is a deliberate tool call rather than an absence of one, so "no tool call" from a
    provider quirk or a confused model is never mistaken for a considered conclusion.
    """

    model_config = ConfigDict(extra="forbid")

    root_cause: str = Field(min_length=1)
    confidence: Literal["low", "medium", "high"] = "medium"
    summary: str | None = None
