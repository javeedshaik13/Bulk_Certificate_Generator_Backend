import os
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.logging import logger
from app.schemas.job import JobCreateRequest, JobCreateResponse, JobDetailResponse
from app.services.job_service import JobService

router = APIRouter(prefix="/certificate-jobs", tags=["Certificate Jobs"])


@router.post(
    "",
    response_model=JobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit bulk certificate generation job",
    description="Submits a bulk certificate request. Validates data, initializes the job in the database, and begins asynchronous processing."
)
def create_certificate_job(
    payload: JobCreateRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db)
):
    try:
        job = JobService.create_bulk_job(db, payload)
        # Schedule background processing worker
        background_tasks.add_task(JobService.process_job_async, job.id)

        base_url = str(request.base_url).rstrip("/")
        status_url = f"{base_url}/api/v1/certificate-jobs/{job.id}"

        return JobCreateResponse(
            job_id=job.id,
            status=job.status,
            message="Certificate generation job accepted for processing.",
            total_recipients=job.total_recipients,
            status_url=status_url
        )
    except Exception as e:
        logger.error("Failed to submit bulk certificate job: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initiate bulk certificate generation job."
        )


@router.get(
    "/{job_id}",
    response_model=JobDetailResponse,
    summary="Get job status and recipient details",
    description="Retrieves the current execution progress, counters, recipient statuses, and download links for a given job ID."
)
def get_job_status(
    job_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    base_url = str(request.base_url).rstrip("/")
    job_detail = JobService.get_job_detail(db, job_id, base_url)
    if not job_detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Certificate job with ID '{job_id}' not found."
        )
    return job_detail


@router.get(
    "/{job_id}/zip",
    summary="Download bulk certificates ZIP archive",
    description="Downloads a compressed ZIP archive containing all successfully generated PDF certificates for the specified job."
)
def download_job_zip(
    job_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    zip_path = JobService.generate_job_zip(db, job_id)
    if not zip_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No successful certificates found for job '{job_id}' to create a ZIP archive."
        )

    # Schedule cleanup of the temporary zip file after response streaming completes
    def _cleanup():
        if os.path.exists(zip_path):
            try:
                os.remove(zip_path)
            except OSError:
                pass

    background_tasks.add_task(_cleanup)

    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename=f"certificates_job_{job_id[:8]}.zip"
    )
