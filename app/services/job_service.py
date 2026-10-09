import asyncio
import io
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Set
from email_validator import validate_email, EmailNotValidError
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging import logger
from app.models.job import GenerationJob, JobStatus
from app.models.recipient import CertificateRecipient, RecipientStatus
from app.schemas.job import JobCreateRequest, JobDetailResponse, JobSummaryResponse
from app.schemas.recipient import RecipientResponse
from app.services.generator_service import process_single_recipient, sanitize_filename
from app.storage.local_storage import storage_service


def validate_recipient_data(
    name: str,
    email: str,
    seen_emails: Set[str],
    duplicate_policy: str = "mark_failed"
) -> tuple[bool, Optional[str], Optional[str]]:
    """
    Validates recipient records at the individual item level.
    Returns (is_valid, error_code, error_message).
    """
    clean_name = name.strip() if name else ""
    if not clean_name:
        return False, "INVALID_NAME", "Recipient name cannot be blank."

    clean_email = email.strip() if email else ""
    if not clean_email:
        return False, "INVALID_EMAIL", "Recipient email cannot be blank."

    try:
        # Syntax check without remote DNS query
        valid = validate_email(clean_email, check_deliverability=False)
        normalized_email = valid.normalized.lower()
    except EmailNotValidError as e:
        return False, "INVALID_EMAIL", f"Invalid email format: {str(e)}"

    if duplicate_policy != "allow" and normalized_email in seen_emails:
        if duplicate_policy == "deduplicate":
            return False, "DEDUPLICATED", f"Recipient '{clean_email}' skipped per batch deduplication policy."
        return False, "DUPLICATE_RECIPIENT_IN_BATCH", f"Duplicate email address '{clean_email}' in the same batch."

    seen_emails.add(normalized_email)
    return True, None, None


class JobService:
    @staticmethod
    def create_bulk_job(db: Session, request: JobCreateRequest) -> GenerationJob:
        """
        Creates a new bulk generation job and its recipient records.
        Evaluates recipient-level validation upfront, isolating invalid entries.
        """
        job_id = str(uuid.uuid4())
        total = len(request.recipients)
        seen_emails: Set[str] = set()

        recipients_to_create: List[CertificateRecipient] = []
        initial_failed = 0
        initial_pending = 0

        for item in request.recipients:
            is_valid, err_code, err_msg = validate_recipient_data(
                item.name,
                item.email,
                seen_emails,
                duplicate_policy=request.duplicate_policy
            )
            recipient_id = str(uuid.uuid4())
            if is_valid:
                rec_status = RecipientStatus.PENDING.value
                initial_pending += 1
            else:
                rec_status = RecipientStatus.FAILED.value
                initial_failed += 1

            recipient = CertificateRecipient(
                id=recipient_id,
                job_id=job_id,
                recipient_name=item.name.strip(),
                recipient_email=item.email.strip(),
                status=rec_status,
                error_code=err_code,
                error_message=err_msg
            )
            recipients_to_create.append(recipient)

        # Initial job status
        if initial_pending == 0:
            initial_job_status = JobStatus.FAILED.value
        else:
            initial_job_status = JobStatus.PENDING.value

        job = GenerationJob(
            id=job_id,
            event_name=request.event_name,
            issue_date=request.issue_date,
            status=initial_job_status,
            total_recipients=total,
            pending_count=initial_pending,
            processing_count=0,
            successful_count=0,
            failed_count=initial_failed
        )

        db.add(job)
        db.add_all(recipients_to_create)
        db.commit()
        db.refresh(job)

        logger.info(
            "Created Job %s with %d recipients (%d pending, %d upfront validation failed)",
            job_id, total, initial_pending, initial_failed
        )
        return job

    @staticmethod
    async def process_job_async(job_id: str):
        """
        Background task worker to process all pending recipients for a job.
        Uses an asyncio Semaphore to bound concurrency.
        """
        logger.info("Starting background processing for Job %s", job_id)
        # Open separate isolated session for the background task
        db = SessionLocal()
        try:
            job = db.get(GenerationJob, job_id)
            if not job:
                logger.error("Job %s not found in background processor", job_id)
                return

            if job.status == JobStatus.FAILED.value and job.pending_count == 0:
                logger.info("Job %s had 0 valid recipients, already finalized as FAILED", job_id)
                job.completed_at = datetime.now(timezone.utc)
                db.commit()
                return

            job.status = JobStatus.PROCESSING.value
            db.commit()

            # Query all PENDING recipients
            stmt = select(CertificateRecipient).where(
                CertificateRecipient.job_id == job_id,
                CertificateRecipient.status == RecipientStatus.PENDING.value
            )
            pending_recipients = db.scalars(stmt).all()

            semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_WORKERS)

            async def _process_recipient_bounded(recipient_id: str, event_name: str, issue_date):
                async with semaphore:
                    # Run CPU-bound ReportLab and disk I/O in worker thread with fresh short-lived session
                    def _sync_worker():
                        thread_db = SessionLocal()
                        try:
                            rec = thread_db.get(CertificateRecipient, recipient_id)
                            if rec:
                                process_single_recipient(thread_db, rec, event_name, issue_date)
                        finally:
                            thread_db.close()

                    await asyncio.to_thread(_sync_worker)

            # Launch all bounded tasks
            tasks = [
                _process_recipient_bounded(r.id, job.event_name, job.issue_date)
                for r in pending_recipients
            ]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

            # Expire session identity cache and re-query counts directly from persisted database state
            db.expire_all()
            success_count = db.scalar(
                select(func.count(CertificateRecipient.id)).where(
                    CertificateRecipient.job_id == job_id,
                    CertificateRecipient.status == RecipientStatus.SUCCESS.value
                )
            ) or 0

            fail_count = db.scalar(
                select(func.count(CertificateRecipient.id)).where(
                    CertificateRecipient.job_id == job_id,
                    CertificateRecipient.status == RecipientStatus.FAILED.value
                )
            ) or 0

            job.pending_count = 0
            job.processing_count = 0
            job.successful_count = success_count
            job.failed_count = fail_count
            job.completed_at = datetime.now(timezone.utc)

            # Determine terminal state
            if success_count == job.total_recipients:
                job.status = JobStatus.COMPLETED.value
            elif success_count > 0:
                job.status = JobStatus.PARTIALLY_COMPLETED.value
            else:
                job.status = JobStatus.FAILED.value

            db.commit()
            logger.info(
                "Finalized Job %s: status=%s, success=%d, failed=%d, total=%d",
                job_id, job.status, success_count, fail_count, job.total_recipients
            )

        except Exception as e:
            logger.critical("Unexpected error in background job %s: %s", job_id, e, exc_info=True)
            try:
                db.rollback()
                job = db.get(GenerationJob, job_id)
                if job:
                    job.status = JobStatus.FAILED.value
                    job.error_summary = f"Fatal worker exception: {str(e)[:255]}"
                    job.completed_at = datetime.now(timezone.utc)
                    db.commit()
            except Exception:
                pass
        finally:
            db.close()

    @staticmethod
    def get_job_summary(db: Session, job_id: str, base_url: str = "") -> Optional[JobSummaryResponse]:
        job = db.get(GenerationJob, job_id)
        if not job:
            return None

        # Build dynamic live counts directly from recipient rows to ensure zero inconsistency
        success_count = db.scalar(
            select(func.count(CertificateRecipient.id)).where(
                CertificateRecipient.job_id == job_id,
                CertificateRecipient.status == RecipientStatus.SUCCESS.value
            )
        ) or 0
        fail_count = db.scalar(
            select(func.count(CertificateRecipient.id)).where(
                CertificateRecipient.job_id == job_id,
                CertificateRecipient.status == RecipientStatus.FAILED.value
            )
        ) or 0
        processing_count = db.scalar(
            select(func.count(CertificateRecipient.id)).where(
                CertificateRecipient.job_id == job_id,
                CertificateRecipient.status == RecipientStatus.PROCESSING.value
            )
        ) or 0
        pending_count = db.scalar(
            select(func.count(CertificateRecipient.id)).where(
                CertificateRecipient.job_id == job_id,
                CertificateRecipient.status == RecipientStatus.PENDING.value
            )
        ) or 0

        zip_url = f"{base_url}/api/v1/certificate-jobs/{job.id}/zip" if success_count > 0 else None

        return JobSummaryResponse(
            id=job.id,
            event_name=job.event_name,
            issue_date=job.issue_date,
            status=job.status,
            total_recipients=job.total_recipients,
            pending_count=pending_count,
            processing_count=processing_count,
            successful_count=success_count,
            failed_count=fail_count,
            created_at=job.created_at,
            updated_at=job.updated_at,
            completed_at=job.completed_at,
            zip_download_url=zip_url
        )

    @staticmethod
    def get_job_detail(db: Session, job_id: str, base_url: str = "") -> Optional[JobDetailResponse]:
        summary = JobService.get_job_summary(db, job_id, base_url)
        if not summary:
            return None

        stmt = select(CertificateRecipient).where(
            CertificateRecipient.job_id == job_id
        ).order_by(CertificateRecipient.created_at)
        recipients = db.scalars(stmt).all()

        recipient_responses = []
        for r in recipients:
            download_url = None
            if r.certificate_id and r.status == RecipientStatus.SUCCESS.value:
                download_url = f"{base_url}/api/v1/certificates/{r.certificate_id}"

            recipient_responses.append(
                RecipientResponse(
                    id=r.id,
                    recipient_name=r.recipient_name,
                    recipient_email=r.recipient_email,
                    status=r.status,
                    certificate_id=r.certificate_id,
                    download_url=download_url,
                    error_code=r.error_code,
                    error_message=r.error_message
                )
            )

        return JobDetailResponse(
            **summary.model_dump(),
            recipients=recipient_responses
        )

    @staticmethod
    def generate_job_zip(db: Session, job_id: str) -> Optional[Path]:
        """
        Generates a ZIP archive on disk containing all successful certificate PDFs.
        Returns the path to the temporary ZIP file.
        """
        job = db.get(GenerationJob, job_id)
        if not job:
            return None

        stmt = select(CertificateRecipient).where(
            CertificateRecipient.job_id == job_id,
            CertificateRecipient.status == RecipientStatus.SUCCESS.value
        )
        successful_recipients = db.scalars(stmt).all()

        if not successful_recipients:
            return None

        temp_zip = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        temp_zip_path = Path(temp_zip.name)
        temp_zip.close()

        try:
            with zipfile.ZipFile(temp_zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for rec in successful_recipients:
                    if rec.storage_key and storage_service.file_exists(rec.storage_key):
                        file_path = storage_service.get_file_path(rec.storage_key)
                        safe_base = sanitize_filename(rec.recipient_name)[:64]
                        safe_entry_name = f"{safe_base}_{rec.certificate_id}.pdf"
                        zip_file.write(file_path, arcname=safe_entry_name)
            return temp_zip_path
        except Exception as e:
            logger.error("Failed to generate zip for job %s: %s", job_id, e)
            if temp_zip_path.exists():
                try:
                    temp_zip_path.unlink()
                except OSError:
                    pass
            raise
