"""Tests for multimodal evidence processing engine and inconclusive fallback handling."""

import unittest
from backend.models.attachments import EvidenceAttachment
from backend.services.evidence_processor import EvidenceProcessor


class MultimodalEvidenceProcessorTests(unittest.TestCase):
    def test_image_product_extraction_succeeds(self) -> None:
        att = EvidenceAttachment(
            case_id="CASE-ORD-9005",
            filename="received_phone2.png",
            file_type="image",
            mime_type="image/png",
            size_bytes=1024,
            storage_path="uploads/cases/CASE-ORD-9005/received_phone2.png",
        )
        # Mock storage file presence
        import os
        os.makedirs("uploads/cases/CASE-ORD-9005", exist_ok=True)
        with open(att.storage_path, "wb") as f:
            f.write(b"mock png bytes")

        result = EvidenceProcessor.process_attachment(att)
        self.assertTrue(result.success)
        self.assertEqual(result.status, "processed")
        self.assertEqual(result.extracted_data.get("visible_product"), "Phone 2")
        self.assertGreater(result.confidence, 0.9)

    def test_unreadable_blurry_image_returns_inconclusive(self) -> None:
        att = EvidenceAttachment(
            case_id="CASE-ORD-9005",
            filename="blurry_photo_unclear.jpg",
            file_type="image",
            mime_type="image/jpeg",
            size_bytes=512,
            storage_path="uploads/cases/CASE-ORD-9005/blurry_photo_unclear.jpg",
        )
        import os
        os.makedirs("uploads/cases/CASE-ORD-9005", exist_ok=True)
        with open(att.storage_path, "wb") as f:
            f.write(b"mock blurry bytes")

        result = EvidenceProcessor.process_attachment(att)
        self.assertFalse(result.success)
        self.assertEqual(result.status, "EVIDENCE_INCONCLUSIVE")
        self.assertEqual(result.extracted_data.get("visible_product"), "UNIDENTIFIED")
        self.assertLess(result.confidence, 0.2)


if __name__ == "__main__":
    unittest.main()
