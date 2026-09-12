"""Read-only payment health tool."""

from backend.data.database import SimulatedCompanyRepository
from backend.models.tools import EmptyInput, ToolResult
from backend.tools.base import ReadOnlyTool


class PaymentStatusTool(ReadOnlyTool[EmptyInput]):
    name = "get_payment_status"
    description = "Get payment success, failure, latency, and top failure reason."
    input_model = EmptyInput

    def execute(self, repository: SimulatedCompanyRepository, arguments: EmptyInput) -> ToolResult:
        data = repository.get_collection("payments")
        return ToolResult.success(self.name, f"Payment failure rate is {data['failure_rate_percent']}%.", data)
