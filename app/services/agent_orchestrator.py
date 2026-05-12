"""룰 기반 intent 분류 및 /ai/chat용 경량 오케스트레이터 (멀티스텝·LLM 의도분석 없음)."""

from __future__ import annotations

import logging
from enum import Enum

from app.core.config import settings
from app.schemas.chat import AgentPayload, ChatRequest, ChatResponseData
from app.services.chat_service import ChatService

__all__ = ["AgentIntent", "AgentOrchestrator"]

logger = logging.getLogger(__name__)


class AgentIntent(str, Enum):
    """에이전트 intent (문자열 값은 API 응답과 동일)."""

    GENERAL_CHAT = "GENERAL_CHAT"
    RAG_SEARCH = "RAG_SEARCH"
    FEATURE_TEMPLATE_HELP = "FEATURE_TEMPLATE_HELP"
    UNKNOWN = "UNKNOWN"


_RAG_HINTS = (
    "문서",
    "검색",
    "찾아",
    "근거",
    "자료",
    "참고",
    "RAG",
    "rag",
)
_FEATURE_HINTS = (
    "기능템플릿",
    "기능 템플릿",
    "템플릿",
    "요구사항",
    "API 명세",
    "api 명세",
    "ERD",
    "erd",
    "면접 질문",
)
_GENERAL_HINTS = (
    "안녕",
    "고마워",
    "뭐해",
    "설명해줘",
    "도와줘",
)

_UNKNOWN_REPLY = (
    "요청 내용을 이해하지 못했습니다. 조금 더 구체적으로 입력해주세요."
)


class AgentOrchestrator:
    """룰 기반 intent 분류 후 ChatService로 위임."""

    @staticmethod
    def classify_intent(message: str) -> str:
        text = (message or "").strip()
        # 1) 빈 문자열 → UNKNOWN
        if not text:
            return AgentIntent.UNKNOWN.value

        lower = text.lower()
        lower_fold = lower.replace(" ", "")

        # 2) 기능템플릿 관련 → FEATURE_TEMPLATE_HELP (RAG 키워드보다 우선)
        for hint in _FEATURE_HINTS:
            h = hint.lower().replace(" ", "")
            if h in lower_fold or hint in text or hint.lower() in lower:
                return AgentIntent.FEATURE_TEMPLATE_HELP.value

        # 3) RAG 관련 → RAG_SEARCH
        for hint in _RAG_HINTS:
            if hint in ("RAG", "rag"):
                if "rag" in lower:
                    return AgentIntent.RAG_SEARCH.value
                continue
            if hint in text:
                return AgentIntent.RAG_SEARCH.value

        # 4) 일반 대화 힌트 → GENERAL_CHAT
        for hint in _GENERAL_HINTS:
            if hint in text:
                return AgentIntent.GENERAL_CHAT.value

        # 5) 기본값 → GENERAL_CHAT
        return AgentIntent.GENERAL_CHAT.value

    async def run_chat(self, request: ChatRequest) -> ChatResponseData:
        intent = self.classify_intent(request.message)
        query_len = len(request.message)
        agent = AgentPayload(
            enabled=True,
            intent=intent,
            mode="rule_based",
        )

        if intent == AgentIntent.UNKNOWN.value:
            logger.info(
                "agent_chat intent=%s apply_rag=false query_len=%s unknown_reply=true",
                intent,
                query_len,
            )
            return ChatResponseData(
                answer=_UNKNOWN_REPLY,
                source="ollama",
                ragUsed=False,
                references=[],
                agent=agent,
            )

        if intent == AgentIntent.RAG_SEARCH.value:
            apply_rag = settings.RAG_ENABLED
            variant = "default"
        elif intent == AgentIntent.FEATURE_TEMPLATE_HELP.value:
            apply_rag = False
            variant = "feature_help"
        else:
            apply_rag = settings.RAG_ENABLED and (request.useRag is True)
            variant = "default"

        logger.info(
            "agent_chat intent=%s apply_rag=%s query_len=%s",
            intent,
            apply_rag,
            query_len,
        )

        return ChatService().answer(
            request,
            apply_rag=apply_rag,
            variant=variant,
            agent=agent,
        )
