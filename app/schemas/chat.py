from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

__all__ = [
    "ChatRequest",
    "ChatResponseData",
]


class ChatRequest(BaseModel):
    """챗봇 요청 (선택 context·useRag; RAG는 RAG_ENABLED=true일 때만 검색)."""

    message: str = Field(..., description="사용자 질문")
    context: str | None = Field(
        default=None,
        description="선택 참고 문맥 (사용자 직접 입력; 검색 결과 아님)",
    )
    useRag: bool | None = Field(
        default=None,
        description="true 이고 서버 RAG_ENABLED=true일 때만 Retriever 검색 후 프롬프트에 주입",
    )

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("message는 비어 있을 수 없습니다.")
        return stripped


class ChatResponseData(BaseModel):
    answer: str
    source: Literal["ollama", "fallback"]
    ragUsed: bool = Field(
        default=False,
        description="RAG_ENABLED·useRag이 모두 true이고 검색 결과 1건 이상일 때 true",
    )
    references: list[Any] = Field(
        default_factory=list,
        description="RAG 검색 근거(제목·내용·score 등); 미사용 시 빈 배열",
    )
