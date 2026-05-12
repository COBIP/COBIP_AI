"""룰 기반 intent 분류 및 /ai/chat용 경량 오케스트레이터 (멀티스텝·tool calling 없음)."""

from __future__ import annotations

import logging
import time
from typing import Literal, cast

from app.schemas.chat import AgentPayload, AgentTrace, ChatRequest, ChatResponseData
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
        t0 = time.perf_counter()
        result = self._classifier.classify(request.message)
        intent = result.intent
        agent_mode = result.mode
        handler = _HANDLER_MAP[intent]
        handler_name = type(handler).__name__
        steps = list(result.steps) + ["handler_dispatch"]
        trace = AgentTrace(
            classifier=result.classifier_name,
            handler=handler_name,
            llmIntentUsed=result.llm_intent_used,
            steps=steps,
            latencyMs=0,
        )
        agent = AgentPayload(
            enabled=True,
            intent=intent,
            mode=cast(AgentMode, agent_mode),
            trace=trace,
        )
        logger.info(
            "agent_orchestrator dispatch intent=%s mode=%s handler=%s trace_steps=%s",
            intent,
            agent_mode,
            handler_name,
            len(steps),
        )
        out = await handler.handle(request, agent)
        latency_ms = max(0, int((time.perf_counter() - t0) * 1000))
        prev = out.agent.trace
        if prev is not None:
            new_trace = prev.model_copy(update={"latencyMs": latency_ms})
        else:
            new_trace = AgentTrace(
                classifier=result.classifier_name,
                handler=handler_name,
                llmIntentUsed=result.llm_intent_used,
                steps=steps,
                latencyMs=latency_ms,
            )
        return out.model_copy(
            update={"agent": out.agent.model_copy(update={"trace": new_trace})}
        )
