"""API routes for customer case evidence attachment handling."""

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from backend.models.attachments import EvidenceAttachment
from backend.services.attachment_service import AttachmentValidationError, save_attachment

router = APIRouter(prefix="/cases", tags=["case-attachments"])

# Global in-memory store mapping case_id -> list[EvidenceAttachment]
_CASE_ATTACHMENTS: dict[str, list[EvidenceAttachment]] = {}


def register_attachment(attachment: EvidenceAttachment) -> None:
    _CASE_ATTACHMENTS.setdefault(attachment.case_id, []).append(attachment)


def get_case_attachments(case_id: str) -> list[EvidenceAttachment]:
    return _CASE_ATTACHMENTS.get(case_id, [])


@router.post("/{case_id}/attachments", response_model=EvidenceAttachment)
async def upload_case_attachment(case_id: str, file: UploadFile = File(...)) -> EvidenceAttachment:
    """Upload an image or document evidence attachment for a customer case."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename missing.")

    try:
        contents = await file.read()
        size_bytes = len(contents)
        import io

        attachment = save_attachment(
            case_id=case_id,
            filename=file.filename,
            file_obj=io.BytesIO(contents),
            size_bytes=size_bytes,
        )
        register_attachment(attachment)
        return attachment
    except AttachmentValidationError as err:
        raise HTTPException(status_code=400, detail=str(err))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save attachment: {exc}")


@router.get("/{case_id}/attachments", response_model=list[EvidenceAttachment])
def list_case_attachments(case_id: str) -> list[EvidenceAttachment]:
    """Retrieve metadata for all evidence attachments linked to a case."""
    return get_case_attachments(case_id)


@router.get("/{case_id}/attachments/{attachment_id}/file")
def download_case_attachment(case_id: str, attachment_id: str):
    """Retrieve raw file content for an uploaded attachment."""
    attachments = get_case_attachments(case_id)
    att = next((a for a in attachments if a.attachment_id == attachment_id), None)
    if not att:
        raise HTTPException(status_code=404, detail="Attachment not found.")

    import os
    if not os.path.exists(att.storage_path):
        raise HTTPException(status_code=404, detail="Attachment file content unavailable.")

    return FileResponse(att.storage_path, media_type=att.mime_type, filename=att.filename)
