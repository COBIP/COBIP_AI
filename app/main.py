"""
FastAPI 앱 엔트리포인트.
USE_MOCK 설정에 따라 Mock / 실제 구현체를 선택해 주입한다.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat_router import init_router, router
from app.config import settings
from app.service.rag_chat_service import RAGChatService


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작 시 서비스 의존성을 초기화한다."""

    if settings.use_mock:
        from app.llm.mock_llm_client import MockLLMClient
        from app.retriever.mock_retriever import MockRetriever

        retriever = MockRetriever()
        llm_client = MockLLMClient()
        print("[COBIP AI] Mock 모드로 시작합니다.")
    else:
        from app.llm.vllm_client import VLLMClient
        from app.retriever.qdrant_retriever import QdrantRetriever

        retriever = QdrantRetriever()
        llm_client = VLLMClient()
        print(f"[COBIP AI] 실서버 모드 - vLLM: {settings.vllm_base_url}, Qdrant: {settings.qdrant_url}")

    chat_service = RAGChatService(retriever=retriever, llm_client=llm_client)
    init_router(chat_service)

    yield


app = FastAPI(
    title="COBIP AI Server",
    description="코드 학습 플랫폼 AI 서버 - RAG 기반 챗봇",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS: Spring Boot 서비스 서버에서의 요청을 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
