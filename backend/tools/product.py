"""Read-only product catalog lookup tool for exact item specifications and pricing."""

from pydantic import BaseModel, ConfigDict, Field

from backend.data.database import SimulatedCompanyRepository
from backend.models.tools import ToolResult
from backend.tools.base import ReadOnlyTool


class GetProductInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str | None = Field(default=None, description="Product ID (e.g. PR-100)")
    sku: str | None = Field(default=None, description="Product SKU (e.g. SKU-NIMBUS-100)")


class GetProductTool(ReadOnlyTool[GetProductInput]):
    name = "get_product"
    description = "Retrieve exact product catalog details, SKU, brand, model, specifications, and unit pricing."
    input_model = GetProductInput

    def execute(self, repository: SimulatedCompanyRepository, arguments: GetProductInput) -> ToolResult:
        products = repository.get_collection("products")
        matched = []

        if arguments.product_id:
            matched = [p for p in products if p.get("product_id") == arguments.product_id]
        elif arguments.sku:
            matched = [p for p in products if p.get("sku") == arguments.sku]
        else:
            matched = products

        if not matched:
            return ToolResult.failure(self.name, "not_found", "No product found matching the specified query.")

        product = matched[0]
        return ToolResult.success(
            self.name,
            f"Retrieved catalog profile for {product.get('name')} ({product.get('product_id')}).",
            {
                "product_id": product.get("product_id"),
                "sku": product.get("sku", f"SKU-{product.get('product_id')}"),
                "name": product.get("name"),
                "brand": product.get("brand", "TechCorp"),
                "model": product.get("model", "Standard"),
                "category": product.get("category"),
                "price_inr": product.get("unit_price"),
                "specifications": product.get("specifications", "Standard commercial specification"),
            },
        )
