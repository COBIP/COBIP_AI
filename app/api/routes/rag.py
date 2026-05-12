"""RAG 검색·인덱싱 테스트용 라우터 (/ai/chat 미연동)."""

from fastapi import APIRouter

from app.schemas.common import ApiResponse
from app.schemas.rag import (
    RagIndexRequest,
    RagIndexResponseData,
    RetrieveRequest,
    RetrieveResponseData,
)
from app.services.rag_indexing_service import RagIndexingService
from app.services.retriever_service import RetrieverService

router = APIRouter(prefix="/ai/rag", tags=["rag"])


@router.post("/retrieve", response_model=ApiResponse)
def retrieve(request: RetrieveRequest) -> ApiResponse:
    """Qdrant 벡터 검색만 수행한다. Ollama·챗봇 answer 생성 없음."""
    refs = RetrieverService().retrieve(request.query, request.topK)
    data = RetrieveResponseData(
        query=request.query,
        references=refs,
        count=len(refs),
    )
    return ApiResponse(
        success=True,
        message="검색이 완료되었습니다.",
        data=data.model_dump(),
    )


@router.post("/index", response_model=ApiResponse)
def index_documents(request: RagIndexRequest) -> ApiResponse:
    """Qdrant에 검색용 문서를 넣는 수동 인덱싱 API. `/ai/chat` 미연동."""
    data: RagIndexResponseData = RagIndexingService().index(request)
    if data.indexedCount == 0:
        return ApiResponse(
            success=False,
            message="인덱싱에 실패했습니다. Qdrant·임베딩·컬렉션 설정을 확인하세요.",
            data=data.model_dump(),
        )
    return ApiResponse(
        success=True,
        message="문서가 인덱싱되었습니다.",
        data=data.model_dump(),
    )
