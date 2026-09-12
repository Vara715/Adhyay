"""Read-only analytics tools over simulated sales and orders."""

from backend.data.database import SimulatedCompanyRepository
from backend.models.tools import EmptyInput, ProductSalesInput, ToolResult
from backend.tools.base import ReadOnlyTool


class RevenueMetricsTool(ReadOnlyTool[EmptyInput]):
    name = "get_revenue_metrics"
    description = "Get current revenue and its comparison with the prior period."
    input_model = EmptyInput

    def execute(self, repository: SimulatedCompanyRepository, arguments: EmptyInput) -> ToolResult:
        data = repository.get_collection("sales")
        return ToolResult.success(self.name, f"Revenue changed {data['change_percent']}% versus the previous period.", data)


class OrderMetricsTool(ReadOnlyTool[EmptyInput]):
    name = "get_order_metrics"
    description = "Get order volume, conversion, cancellation, and order-value metrics."
    input_model = EmptyInput

    def execute(self, repository: SimulatedCompanyRepository, arguments: EmptyInput) -> ToolResult:
        data = repository.get_collection("orders")
        return ToolResult.success(self.name, f"Order volume is {data['current_orders']} for {data['period']}.", data)


class ProductSalesTool(ReadOnlyTool[ProductSalesInput]):
    name = "get_product_sales"
    description = "Get product sales performance, optionally filtered by product or category."
    input_model = ProductSalesInput

    def execute(self, repository: SimulatedCompanyRepository, arguments: ProductSalesInput) -> ToolResult:
        products = repository.get_collection("products")
        if arguments.product_id:
            products = [item for item in products if item["product_id"] == arguments.product_id]
        if arguments.category:
            products = [item for item in products if item["category"].lower() == arguments.category.lower()]
        if not products:
            return ToolResult.failure(self.name, "not_found", "No products match the supplied filter.")
        return ToolResult.success(self.name, f"Returned sales performance for {len(products)} product(s).", {"products": products})
