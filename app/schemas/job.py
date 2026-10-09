from datetime import date, datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, field_validator, ConfigDict
from app.core.config import settings
from app.schemas.recipient import RecipientInput, RecipientResponse


class JobCreateRequest(BaseModel):
    event_name: str = Field(..., min_length=1, max_length=255, description="Name of the course, workshop or event")
    issue_date: date = Field(..., description="Issue date in YYYY-MM-DD format")
    duplicate_policy: Literal["mark_failed", "deduplicate", "allow"] = Field(
        default="mark_failed",
        description="Policy for handling duplicate recipient emails within the batch: 'mark_failed' (default), 'deduplicate' (keep only first), or 'allow' (generate certificate for each entry)"
    )
    recipients: List[RecipientInput] = Field(
        ...,
        min_length=1,
        description=f"List of certificate recipients (up to {settings.MAX_RECIPIENTS_PER_JOB})"
    )

    @field_validator("event_name")
    @classmethod
    def validate_event_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("event_name cannot be blank.")
        return cleaned

    @field_validator("recipients")
    @classmethod
    def validate_recipients_count(cls, v: List[RecipientInput]) -> List[RecipientInput]:
        if len(v) == 0:
            raise ValueError("Recipients list cannot be empty.")
        if len(v) > settings.MAX_RECIPIENTS_PER_JOB:
            raise ValueError(f"Recipients count exceeds maximum allowed limit of {settings.MAX_RECIPIENTS_PER_JOB}.")
        return v


class JobCreateResponse(BaseModel):
    job_id: str
    status: str
    message: str
    total_recipients: int
    status_url: str


class JobSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_name: str
    issue_date: date
    status: str
    total_recipients: int
    pending_count: int
    processing_count: int
    successful_count: int
    failed_count: int
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    zip_download_url: Optional[str] = None


class JobDetailResponse(JobSummaryResponse):
    recipients: List[RecipientResponse] = []
