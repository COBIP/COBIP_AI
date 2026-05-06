from pydantic import BaseModel

__all__ = [
    "ChatRequest",
    "ChatResponse",
]


class ChatRequest(BaseModel):
    message: str
    context: dict | None = None
    userId: str | None = None


class ChatResponse(BaseModel):
    answer: str
    references: list[dict] = []
