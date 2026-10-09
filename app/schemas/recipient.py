from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class RecipientInput(BaseModel):
    name: str = Field(..., description="Full name of recipient")
    email: str = Field(..., description="Email address of recipient")


class RecipientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    recipient_name: str
    recipient_email: str
    status: str
    certificate_id: Optional[str] = None
    download_url: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
