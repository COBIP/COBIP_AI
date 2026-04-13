"""
API 라우터.
Spring Boot 서비스 서버가 호출하는 엔드포인트를 정의한다.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.data.problem_store import get_all_problems, get_problem
from app.dto.schemas import ChatRequest, ChatResponse, ProblemDTO, WrongPatternDTO
from app.service.rag_chat_service import RAGChatService

router = APIRouter(prefix="/api", tags=["AI Chat"])

# main.py에서 주입
_chat_service: RAGChatService | None = None


def init_router(chat_service: RAGChatService) -> None:
    """main.py에서 서비스 인스턴스를 주입한다."""
    global _chat_service
    _chat_service = chat_service


@router.get("/health")
async def health_check():
    return {"status": "ok", "service": "COBIP AI Server"}


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """RAG 기반 챗봇 질문 처리"""
    if _chat_service is None:
        raise HTTPException(status_code=500, detail="Chat service not initialized")
    return await _chat_service.chat(request)


@router.get("/problems", response_model=list[ProblemDTO])
async def list_problems():
    """전체 문제 목록 조회"""
    problems = get_all_problems()
    return [
        ProblemDTO(
            id=p.id,
            title=p.title,
            description=p.description,
            answer_code=p.answer_code,
            concept=p.concept,
            hint=p.hint,
            wrong_patterns=[
                WrongPatternDTO(
                    error_type=wp.error_type,
                    pattern=wp.pattern,
                    feedback=wp.feedback,
                )
                for wp in p.wrong_patterns
            ],
            explanation_chunks=p.explanation_chunks,
        )
        for p in problems
    ]


@router.get("/problems/{problem_id}", response_model=ProblemDTO)
async def get_problem_detail(problem_id: int):
    """문제 상세 조회"""
    p = get_problem(problem_id)
    if p is None:
        raise HTTPException(status_code=404, detail=f"Problem {problem_id} not found")
    return ProblemDTO(
        id=p.id,
        title=p.title,
        description=p.description,
        answer_code=p.answer_code,
        concept=p.concept,
        hint=p.hint,
        wrong_patterns=[
            WrongPatternDTO(
                error_type=wp.error_type,
                pattern=wp.pattern,
                feedback=wp.feedback,
            )
            for wp in p.wrong_patterns
        ],
        explanation_chunks=p.explanation_chunks,
    )
