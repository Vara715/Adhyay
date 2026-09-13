"""Tests for safe evidence attachment upload service and API security."""

import io
import unittest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.attachment_service import AttachmentValidationError, save_attachment

client = TestClient(app)


class AttachmentUploadTests(unittest.TestCase):
    def test_valid_image_upload_succeeds(self) -> None:
        file_bytes = b"fake image bytes content"
        attachment = save_attachment(
            case_id="CASE-TEST-100",
            filename="received_phone2.jpg",
            file_obj=io.BytesIO(file_bytes),
            size_bytes=len(file_bytes),
        )
        self.assertEqual(attachment.case_id, "CASE-TEST-100")
        self.assertEqual(attachment.filename, "received_phone2.jpg")
        self.assertEqual(attachment.file_type, "image")
        self.assertEqual(attachment.mime_type, "image/jpeg")

    def test_unsupported_file_extension_rejected(self) -> None:
        with self.assertRaisesRegex(AttachmentValidationError, "Unsupported file extension"):
            save_attachment(
                case_id="CASE-TEST-101",
                filename="script.exe",
                file_obj=io.BytesIO(b"binary"),
                size_bytes=6,
            )

    def test_oversized_file_rejected(self) -> None:
        huge_size = 11 * 1024 * 1024  # 11 MB
        with self.assertRaisesRegex(AttachmentValidationError, "exceeds maximum allowed limit"):
            save_attachment(
                case_id="CASE-TEST-102",
                filename="large.png",
                file_obj=io.BytesIO(b""),
                size_bytes=huge_size,
            )

    def test_filename_sanitization_prevents_path_traversal(self) -> None:
        attachment = save_attachment(
            case_id="CASE-TEST-103",
            filename="../../../etc/passwd.png",
            file_obj=io.BytesIO(b"data"),
            size_bytes=4,
        )
        self.assertEqual(attachment.filename, "passwd.png")
        self.assertNotIn("..", attachment.storage_path)

    def test_upload_api_endpoint(self) -> None:
        files = {"file": ("invoice.pdf", b"PDF invoice content data ORD-9005", "application/pdf")}
        res = client.post("/api/cases/CASE-ORD-9005/attachments", files=files)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["filename"], "invoice.pdf")
        self.assertEqual(data["file_type"], "document")


if __name__ == "__main__":
    unittest.main()
