"""Provider-neutral request and response contracts for the LLM boundary."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.models.tools import ToolCall, ToolMetadata


class LLMMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant", "tool"]
    content: str = Field(min_length=1)


class LLMRequest(BaseModel):
    """The compact request shape every provider adapter must accept."""

    model_config = ConfigDict(extra="forbid")

    messages: list[LLMMessage] = Field(min_length=1)
    tools: list[ToolMetadata] = Field(default_factory=list)


class LLMResponse(BaseModel):
    """A provider-normalized response containing text or exactly one tool call."""

    model_config = ConfigDict(extra="forbid")

    content: str | None = None
    tool_call: ToolCall | None = None

    @model_validator(mode="after")
    def require_response_content(self) -> "LLMResponse":
        if not self.content and self.tool_call is None:
            raise ValueError("LLM response must contain content or a tool call.")
        return self
