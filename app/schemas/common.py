from typing import Optional, Any
from pydantic import BaseModel


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    details: Optional[Any] = None
