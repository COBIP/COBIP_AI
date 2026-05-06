from typing import Any

from pydantic import BaseModel, Field


class ApiResponse(BaseModel):
    success: bool
    message: str
    data: Any | None = None


class ErrorResponse(BaseModel):
    success: bool = False
    message: str
    errorCode: str = Field(..., description="에러 코드 식별자")
    details: dict[str, Any] | None = None
