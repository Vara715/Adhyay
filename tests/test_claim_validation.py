"""Tests for evidence fusion and claim validation (SUPPORTED, CONTRADICTED, INCONCLUSIVE)."""

import unittest
from backend.models.attachments import EvidenceAttachment
from backend.services.claim_validator import ClaimValidator


class ClaimValidationTests(unittest.TestCase):
    def test_wrong_product_received_claim_is_supported(self) -> None:
        att = EvidenceAttachment(
            case_id="CASE-ORD-9005",
            filename="received_phone2.png",
            file_type="image",
            mime_type="image/png",
            size_bytes=1024,
            storage_path="uploads/cases/CASE-ORD-9005/received_phone2.png",
        )
        import os
        os.makedirs("uploads/cases/CASE-ORD-9005", exist_ok=True)
        with open(att.storage_path, "wb") as f:
            f.write(b"mock data")

        order_data = {"order_id": "ORD-9005", "product_name": "Phone 1"}
        assessment = ClaimValidator.evaluate_claim(
            goal="I ordered Phone 1 but received Phone 2.",
            order_data=order_data,
            attachments=[att],
        )
        self.assertEqual(assessment.claim_status, "SUPPORTED")
        self.assertIn("Phone 2", assessment.observed_value or "")

    def test_blurry_photo_results_in_inconclusive_status(self) -> None:
        att = EvidenceAttachment(
            case_id="CASE-ORD-9005",
            filename="blurry_unclear_photo.jpg",
            file_type="image",
            mime_type="image/jpeg",
            size_bytes=512,
            storage_path="uploads/cases/CASE-ORD-9005/blurry_unclear_photo.jpg",
        )
        import os
        os.makedirs("uploads/cases/CASE-ORD-9005", exist_ok=True)
        with open(att.storage_path, "wb") as f:
            f.write(b"mock data")

        order_data = {"order_id": "ORD-9005", "product_name": "Phone 1"}
        assessment = ClaimValidator.evaluate_claim(
            goal="I ordered Phone 1 but received Phone 2.",
            order_data=order_data,
            attachments=[att],
        )
        self.assertEqual(assessment.claim_status, "INCONCLUSIVE")
        self.assertIn("blurry", assessment.reason.lower())


if __name__ == "__main__":
    unittest.main()
