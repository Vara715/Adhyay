"""Read-only supplier status tool."""

from backend.data.database import SimulatedCompanyRepository
from backend.models.tools import SupplierStatusInput, ToolResult
from backend.tools.base import ReadOnlyTool


class SupplierStatusTool(ReadOnlyTool[SupplierStatusInput]):
    name = "get_supplier_status"
    description = "Get supplier shipment status and delivery delays."
    input_model = SupplierStatusInput

    def execute(self, repository: SimulatedCompanyRepository, arguments: SupplierStatusInput) -> ToolResult:
        suppliers = repository.get_collection("suppliers")
        if arguments.supplier_id:
            suppliers = [item for item in suppliers if item["supplier_id"] == arguments.supplier_id]
        if not suppliers:
            return ToolResult.failure(self.name, "not_found", "No suppliers match the supplied supplier_id.")
        return ToolResult.success(self.name, f"Returned status for {len(suppliers)} supplier(s).", {"suppliers": suppliers})
