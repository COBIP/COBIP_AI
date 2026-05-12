"""Intent별 /ai/chat 처리 핸들러 (구조 분리; 멀티스텝·LLM 분류·tool calling 없음)."""

from __future__ import annotations

import logging

from app.core.config import settings
from app.schemas.chat import AgentPayload, ChatRequest, ChatResponseData
from app.services.chat_service import ChatService

__all__ = [
    "FeatureTemplateHelpHandler",
    "GeneralChatHandler",
    "RagSearchHandler",
    "UnknownHandler",
]

logger = logging.getLogger(__name__)

_UNKNOWN_REPLY = (
    "요청 내용을 이해하지 못했습니다. 조금 더 구체적으로 입력해주세요."
)


class GeneralChatHandler:
    """일반 대화: useRag=true 이고 RAG_ENABLED=true일 때만 RAG."""

    async def handle(self, request: ChatRequest, agent: AgentPayload) -> ChatResponseData:
        apply_rag = settings.RAG_ENABLED and (request.useRag is True)
        query_len = len(request.message)
        logger.info(
            "agent_handler general_chat apply_rag=%s query_len=%s",
            apply_rag,
            query_len,
        )
        return ChatService().answer(
            request,
            apply_rag=apply_rag,
            variant="default",
            agent=agent,
        )


class RagSearchHandler:
    """RAG 검색 의도: RAG_ENABLED이면 Retriever 사용."""

    async def handle(self, request: ChatRequest, agent: AgentPayload) -> ChatResponseData:
        apply_rag = settings.RAG_ENABLED
        query_len = len(request.message)
        logger.info(
            "agent_handler rag_search apply_rag=%s query_len=%s",
            apply_rag,
            query_len,
        )
        return ChatService().answer(
            request,
            apply_rag=apply_rag,
            variant="default",
            agent=agent,
        )


class FeatureTemplateHelpHandler:
    """기능 템플릿 안내: feature_help variant, RAG 기본 비활성."""

    async def handle(self, request: ChatRequest, agent: AgentPayload) -> ChatResponseData:
        query_len = len(request.message)
        logger.info(
            "agent_handler feature_template_help apply_rag=false query_len=%s",
            query_len,
        )
        return ChatService().answer(
            request,
            apply_rag=False,
            variant="feature_help",
            agent=agent,
        )


class UnknownHandler:
    """UNKNOWN: LLM 없이 고정 안내."""

    async def handle(self, request: ChatRequest, agent: AgentPayload) -> ChatResponseData:
        query_len = len(request.message)
        logger.info(
            "agent_handler unknown apply_rag=false query_len=%s unknown_reply=true",
            query_len,
        )
        return ChatResponseData(
            answer=_UNKNOWN_REPLY,
            source="ollama",
            ragUsed=False,
            references=[],
            agent=agent,
        )
