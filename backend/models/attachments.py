"""Typed evidence attachment models for customer upload handling."""

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

AttachmentFileType = Literal["image", "document", "other"]
AttachmentStatus = Literal["uploaded", "processing", "processed", "inconclusive", "error"]


class EvidenceAttachment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attachment_id: str = Field(default_factory=lambda: f"ATT-{uuid4().hex[:8]}")
    case_id: str
    filename: str
    file_type: AttachmentFileType
    mime_type: str
    size_bytes: int
    storage_path: str
    upload_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: AttachmentStatus = "uploaded"
    extracted_text: str | None = None
    extracted_data: dict[str, Any] = Field(default_factory=dict)
