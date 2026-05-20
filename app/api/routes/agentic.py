from fastapi import APIRouter

from app.schemas.agentic import AgenticRagRequest
from app.schemas.common import ApiResponse
from app.services.agent_orchestrator import AgentOrchestrator

router = APIRouter(prefix="/ai/agentic-rag", tags=["agentic-rag"])


@router.post("/run", response_model=ApiResponse)
async def run_agentic_rag(request: AgenticRagRequest) -> ApiResponse:
    result = await AgentOrchestrator().run_agentic_rag(request)
    return ApiResponse(
        success=True,
        message="Agentic RAG 처리가 완료되었습니다.",
        data=result.model_dump(),
    )
