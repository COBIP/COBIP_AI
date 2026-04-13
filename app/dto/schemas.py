"""
API 요청/응답 DTO (Pydantic 모델).
Spring Boot 서비스 서버와 주고받는 데이터 구조를 정의한다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── 요청 DTO ─────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    """Spring Boot → FastAPI: 챗봇 질문 요청"""
    problem_id: int = Field(..., description="문제 ID")
    user_code: str = Field(..., description="사용자가 제출한 코드")
    question: str = Field(..., description="사용자 질문 (예: '왜 틀렸나요?')")


# ── 응답 DTO ─────────────────────────────────────────────────────

class ChatResponse(BaseModel):
    """FastAPI → Spring Boot: 챗봇 답변"""
    answer: str = Field(..., description="LLM이 생성한 답변")
    retrieved_context: list[str] = Field(
        default_factory=list,
        description="RAG로 검색된 context 목록 (디버깅용)",
    )


# ── 내부 데이터 DTO ──────────────────────────────────────────────

class WrongPatternDTO(BaseModel):
    error_type: str
    pattern: str
    feedback: str


class ProblemDTO(BaseModel):
    """문제 조회 응답"""
    id: int
    title: str
    description: str
    answer_code: str
    concept: str
    hint: str
    wrong_patterns: list[WrongPatternDTO] = Field(default_factory=list)
    explanation_chunks: list[str] = Field(default_factory=list)
