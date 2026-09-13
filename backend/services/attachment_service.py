"""Service for safe file upload handling, extension validation, path traversal prevention, and storage management."""

import os
import re
from pathlib import Path
from typing import BinaryIO

from backend.models.attachments import AttachmentFileType, EvidenceAttachment

UPLOAD_DIR = Path("uploads/cases")
ALLOWED_EXTENSIONS = {
    ".jpg": ("image", "image/jpeg"),
    ".jpeg": ("image", "image/jpeg"),
    ".png": ("image", "image/png"),
    ".pdf": ("document", "application/pdf"),
    ".txt": ("document", "text/plain"),
}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB limit


class AttachmentValidationError(ValueError):
    """Raised when an uploaded file violates security or size constraints."""


def sanitize_filename(filename: str) -> str:
    """Strip dangerous characters and path traversal sequences from filenames."""
    filename = os.path.basename(filename)
    filename = re.sub(r"[^\w\.-]", "_", filename)
    return filename or "unnamed_file"


def get_attachment_storage_dir(case_id: str) -> Path:
    """Return the secure local upload directory for a specific case."""
    sanitized_case_id = sanitize_filename(case_id)
    case_dir = UPLOAD_DIR / sanitized_case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    return case_dir


def save_attachment(
    case_id: str,
    filename: str,
    file_obj: BinaryIO,
    size_bytes: int,
) -> EvidenceAttachment:
    """Validate, sanitize, and save an uploaded file securely."""
    if size_bytes > MAX_FILE_SIZE_BYTES:
        raise AttachmentValidationError(
            f"File size ({size_bytes / (1024 * 1024):.2f} MB) exceeds maximum allowed limit of 10 MB."
        )

    clean_name = sanitize_filename(filename)
    ext = Path(clean_name).suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        allowed_str = ", ".join(ALLOWED_EXTENSIONS.keys())
        raise AttachmentValidationError(
            f"Unsupported file extension '{ext}'. Allowed extensions: {allowed_str}"
        )

    file_type, mime_type = ALLOWED_EXTENSIONS[ext]
    storage_dir = get_attachment_storage_dir(case_id)

    attachment = EvidenceAttachment(
        case_id=case_id,
        filename=clean_name,
        file_type=file_type,
        mime_type=mime_type,
        size_bytes=size_bytes,
        storage_path=str(storage_dir / clean_name),
    )

    dest_path = Path(attachment.storage_path)
    file_obj.seek(0)
    with open(dest_path, "wb") as f:
        f.write(file_obj.read())

    return attachment
