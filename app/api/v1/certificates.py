from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.recipient import CertificateRecipient, RecipientStatus
from app.services.generator_service import sanitize_filename
from app.storage.local_storage import storage_service

router = APIRouter(prefix="/certificates", tags=["Certificates"])


@router.get(
    "/{certificate_id}",
    summary="Download single certificate PDF",
    description="Streams or downloads the official generated PDF certificate for the given certificate ID."
)
def download_certificate(
    certificate_id: str,
    db: Session = Depends(get_db)
):
    stmt = select(CertificateRecipient).where(
        CertificateRecipient.certificate_id == certificate_id
    )
    recipient = db.scalars(stmt).first()

    if not recipient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Certificate with ID '{certificate_id}' was not found."
        )

    if recipient.status != RecipientStatus.SUCCESS.value or not recipient.storage_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Certificate '{certificate_id}' is not in a valid completed state."
        )

    if not storage_service.file_exists(recipient.storage_key):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The requested certificate file could not be located on the storage server."
        )

    file_path = storage_service.get_file_path(recipient.storage_key)
    safe_name = sanitize_filename(recipient.recipient_name)[:64]
    download_filename = f"{safe_name}_{recipient.certificate_id}.pdf"

    return FileResponse(
        path=str(file_path),
        media_type="application/pdf",
        filename=download_filename,
        content_disposition_type="inline"
    )
