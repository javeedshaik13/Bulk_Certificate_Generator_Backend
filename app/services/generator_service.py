import re
import uuid
from datetime import date
from typing import Union
from sqlalchemy.orm import Session
from app.core.logging import logger
from app.generator.pdf_engine import generate_certificate_pdf
from app.models.recipient import CertificateRecipient, RecipientStatus
from app.storage.local_storage import storage_service


def sanitize_filename(name: str) -> str:
    """Sanitize name for safe filesystem and archive operations."""
    cleaned = re.sub(r"[^\w\s-]", "", name).strip()
    return re.sub(r"[-\s]+", "_", cleaned) or "recipient"


def process_single_recipient(
    db: Session,
    recipient: CertificateRecipient,
    event_name: str,
    issue_date: Union[date, str]
) -> bool:
    """
    Renders and persists the certificate for a single recipient.
    Guarantees failure isolation: errors are caught, sanitized, and stored
    on the recipient record without raising outward exceptions.
    """
    try:
        # Mark recipient as PROCESSING
        recipient.status = RecipientStatus.PROCESSING.value
        db.add(recipient)
        db.commit()

        # Generate unique certificate identifier
        cert_uuid = str(uuid.uuid4())
        cert_id = f"CERT-{cert_uuid[:8].upper()}-{cert_uuid[9:13].upper()}"

        # 1. Render PDF bytes
        pdf_bytes = generate_certificate_pdf(
            recipient_name=recipient.recipient_name,
            event_name=event_name,
            issue_date=issue_date,
            certificate_id=cert_id
        )

        if not pdf_bytes or len(pdf_bytes) == 0:
            raise ValueError("PDF generator returned empty byte stream.")

        # 2. Persist to storage abstraction (bounded length to avoid OS path limits)
        safe_name = sanitize_filename(recipient.recipient_name)[:64]
        storage_key = f"{cert_id}_{safe_name}.pdf"
        saved_path = storage_service.save_file(pdf_bytes, storage_key)

        # 3. Update recipient to SUCCESS
        recipient.status = RecipientStatus.SUCCESS.value
        recipient.certificate_id = cert_id
        recipient.storage_key = storage_key
        recipient.file_size_bytes = len(pdf_bytes)
        recipient.error_code = None
        recipient.error_message = None
        db.add(recipient)
        db.commit()

        logger.info(
            "Recipient %s certificate generated successfully (ID: %s, size: %d bytes)",
            recipient.id, cert_id, len(pdf_bytes)
        )
        return True

    except Exception as exc:
        logger.error(
            "Failed certificate generation for recipient %s (%s): %s",
            recipient.id, recipient.recipient_name, exc, exc_info=True
        )
        try:
            db.rollback()
            recipient.status = RecipientStatus.FAILED.value
            recipient.error_code = "GENERATION_FAILED"
            # Sanitize error message to prevent leaking internal traces
            clean_msg = str(exc)
            if len(clean_msg) > 255:
                clean_msg = clean_msg[:252] + "..."
            recipient.error_message = clean_msg
            db.add(recipient)
            db.commit()
        except Exception as db_err:
            logger.critical("Database error while recording recipient failure: %s", db_err)
            db.rollback()
        return False
