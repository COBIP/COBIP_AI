from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

__all__ = [
    "AgentPayload",
    "ChatRequest",
    "ChatResponseData",
]


class AgentPayload(BaseModel):
    """룰 기반 에이전트 메타 (/ai/chat)."""

    enabled: bool = Field(default=True, description="에이전트 오케스트레이션 사용 여부")
    intent: str = Field(..., description="분류된 intent (GENERAL_CHAT 등)")
    mode: Literal["rule_based"] = Field(
        default="rule_based",
        description="intent 분류 방식 (현 단계는 rule_based 고정)",
    )


class ChatRequest(BaseModel):
    """챗봇 요청 (선택 context·useRag; RAG는 RAG_ENABLED=true일 때만 검색)."""

    message: str = Field(..., description="사용자 질문")
    context: str | None = Field(
        default=None,
        description="선택 참고 문맥 (사용자 직접 입력; 검색 결과 아님)",
    )
    useRag: bool | None = Field(
        default=None,
        description="GENERAL_CHAT intent일 때만 적용: true 이고 RAG_ENABLED=true이면 Retriever 검색 후 주입",
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
        description="Retriever가 실제로 사용되어 근거가 주입된 경우 true",
    )
    references: list[Any] = Field(
        default_factory=list,
        description="RAG 검색 근거(제목·내용·score 등); 미사용 시 빈 배열",
    )
    agent: AgentPayload = Field(
        ...,
        description="에이전트 메타 (intent·mode 등)",
    )
