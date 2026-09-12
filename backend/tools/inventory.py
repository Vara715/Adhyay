"""Read-only inventory tool."""

from backend.data.database import SimulatedCompanyRepository
from backend.models.tools import InventoryStatusInput, ToolResult
from backend.tools.base import ReadOnlyTool


class InventoryStatusTool(ReadOnlyTool[InventoryStatusInput]):
    name = "get_inventory_status"
    description = "Get stock, reservations, and reorder status for products."
    input_model = InventoryStatusInput

    def execute(self, repository: SimulatedCompanyRepository, arguments: InventoryStatusInput) -> ToolResult:
        items = repository.get_collection("inventory")
        if arguments.product_id:
            items = [item for item in items if item["product_id"] == arguments.product_id]
        if not items:
            return ToolResult.failure(self.name, "not_found", "No inventory records match the supplied product_id.")
        for item in items:
            item["available_to_sell"] = item["on_hand"] - item["reserved"]
            item["below_reorder_point"] = item["on_hand"] <= item["reorder_point"]
        return ToolResult.success(self.name, f"Returned inventory status for {len(items)} product(s).", {"inventory": items})
