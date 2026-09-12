"""Shared validation and failure handling for deterministic read-only tools."""

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from backend.data.database import SimulatedCompanyRepository
from backend.models.tools import ToolMetadata, ToolResult

InputT = TypeVar("InputT", bound=BaseModel)


class ReadOnlyTool(ABC, Generic[InputT]):
    name: str
    description: str
    input_model: type[InputT]

    @property
    def metadata(self) -> ToolMetadata:
        """Expose concise, JSON-schema-backed discovery metadata."""
        return ToolMetadata(
            name=self.name,
            description=self.description,
            input_schema=self.input_model.model_json_schema(),
        )

    def run(self, repository: SimulatedCompanyRepository, arguments: dict[str, Any] | None = None) -> ToolResult:
        try:
            validated = self.input_model.model_validate(arguments if arguments is not None else {})
        except ValidationError as error:
            return ToolResult.failure(self.name, "invalid_input", error.errors()[0]["msg"])

        failure = repository.check_failure(self.name)
        if failure:
            return ToolResult.failure(self.name, failure.code, failure.message, retryable=failure.retryable)

        result = self.execute(repository, validated)
        if result.ok:
            result.warnings = repository.get_warnings(self.name)
        return result

    @abstractmethod
    def execute(self, repository: SimulatedCompanyRepository, arguments: InputT) -> ToolResult:
        """Return a successful normalized response after validated input."""
