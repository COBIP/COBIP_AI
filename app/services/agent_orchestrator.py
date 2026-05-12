"""룰 기반 intent 분류 및 /ai/chat용 경량 오케스트레이터 (멀티스텝·tool calling 없음)."""

from __future__ import annotations

import logging
from typing import Literal, cast

from app.schemas.chat import AgentPayload, ChatRequest, ChatResponseData
from app.services.agent_handlers import (
    FeatureTemplateHelpHandler,
    GeneralChatHandler,
    RagSearchHandler,
    UnknownHandler,
)
from app.services.intent_classifier import AgentIntent, HybridIntentClassifier

__all__ = ["AgentIntent", "AgentOrchestrator"]

logger = logging.getLogger(__name__)

AgentMode = Literal["rule_based", "llm_assisted", "hybrid"]

_HANDLER_MAP = {
    AgentIntent.GENERAL_CHAT.value: GeneralChatHandler(),
    AgentIntent.RAG_SEARCH.value: RagSearchHandler(),
    AgentIntent.FEATURE_TEMPLATE_HELP.value: FeatureTemplateHelpHandler(),
    AgentIntent.UNKNOWN.value: UnknownHandler(),
}


class AgentOrchestrator:
    """Hybrid intent 분류 후 intent별 handler로 위임."""

    _classifier = HybridIntentClassifier()

    async def run_chat(self, request: ChatRequest) -> ChatResponseData:
        intent, agent_mode = self._classifier.classify(request.message)
        agent = AgentPayload(
            enabled=True,
            intent=intent,
            mode=cast(AgentMode, agent_mode),
        )
        handler = _HANDLER_MAP[intent]
        logger.info(
            "agent_orchestrator dispatch intent=%s mode=%s handler=%s",
            intent,
            agent_mode,
            type(handler).__name__,
        )
        return await handler.handle(request, agent)
