"""보조 Q&A 챗봇 라우터 (Ollama 기반, RAG 없음).

⚠️ 챗봇은 이 시스템의 핵심 기능이 아니라 보조 Q&A 기능이다.
핵심은 기능템플릿 생성·문법 문제 생성/채점·미션/면접 피드백이며,
이 라우터의 우선순위는 그보다 항상 낮다.
"""

from fastapi import APIRouter

from app.schemas.chat import ChatRequest
from app.schemas.common import ApiResponse
from app.services.chat_service import ChatService

router = APIRouter(prefix="/ai", tags=["chat"])


@router.post("/chat", response_model=ApiResponse)
def chat(request: ChatRequest) -> ApiResponse:
    result = ChatService().answer(request)
    return ApiResponse(
        success=True,
        message="챗봇 답변이 생성되었습니다.",
        data=result.model_dump(),
    )
