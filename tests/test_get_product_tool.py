"""Tests for dedicated product catalog lookup tool (get_product)."""

import unittest
from backend.data.database import SimulatedCompanyRepository
from backend.tools.product import GetProductInput, GetProductTool


class GetProductToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = SimulatedCompanyRepository()
        self.tool = GetProductTool()

    def test_get_product_by_id(self) -> None:
        result = self.tool.execute(self.repo, GetProductInput(product_id="PR-100"))
        self.assertTrue(result.ok)
        self.assertEqual(result.data["product_id"], "PR-100")
        self.assertEqual(result.data["name"], "Nimbus Wireless Headphones")
        self.assertEqual(result.data["sku"], "SKU-NIMBUS-100")
        self.assertEqual(result.data["brand"], "Nimbus")

    def test_get_product_by_sku(self) -> None:
        result = self.tool.execute(self.repo, GetProductInput(sku="SKU-ATLAS-200"))
        self.assertTrue(result.ok)
        self.assertEqual(result.data["product_id"], "PR-200")
        self.assertEqual(result.data["name"], "Atlas Laptop Stand")

    def test_get_product_not_found(self) -> None:
        result = self.tool.execute(self.repo, GetProductInput(product_id="PR-999"))
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "not_found")


if __name__ == "__main__":
    unittest.main()
