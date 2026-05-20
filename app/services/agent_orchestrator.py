"""룰 기반 intent 분류 및 /ai/chat용 경량 오케스트레이터 (멀티스텝·tool calling 없음)."""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Literal, cast

from app.core.config import settings
from app.models.enums import DifficultyLevel, IntentType
from app.schemas.agentic import (
    AgenticRagRequest,
    AgenticRagResponseData,
    AgenticRagTrace,
)
from app.schemas.chat import AgentPayload, AgentTrace, ChatRequest, ChatResponseData
from app.schemas.feature_template import FeatureTemplateGenerateRequest
from app.services.agent_handlers import (
    FeatureTemplateHelpHandler,
    GeneralChatHandler,
    RagSearchHandler,
    UnknownHandler,
)
from app.services.agent_router import AgentRouter
from app.services.agent_tools import AgentToolRegistry
from app.services.feature_template_generator import FeatureTemplateGenerator
from app.services.intent_classifier import AgentIntent, HybridIntentClassifier
from app.services.retriever_service import RetrieverService

__all__ = ["AgentIntent", "AgentOrchestrator"]

logger = logging.getLogger(__name__)

AgentMode = Literal["rule_based", "llm_assisted", "hybrid"]

_TOOL_REGISTRY = AgentToolRegistry()

_HANDLER_MAP = {
    AgentIntent.GENERAL_CHAT.value: GeneralChatHandler(),
    AgentIntent.RAG_SEARCH.value: RagSearchHandler(),
    AgentIntent.FEATURE_TEMPLATE_HELP.value: FeatureTemplateHelpHandler(),
    AgentIntent.UNKNOWN.value: UnknownHandler(),
}

_FEATURE_GENERATE_HINTS = (
    "기능템플릿",
    "기능 템플릿",
    "템플릿 생성",
    "기능 명세",
    "요구사항",
)
_FEATURE_ACTION_HINTS = (
    "생성",
    "만들",
    "작성",
    "뽑아",
    "설계",
)
_RAG_HINTS = (
    "문서",
    "검색",
    "근거",
    "자료",
    "참고",
    "rag",
)
_LANGUAGE_HINTS = {
    "python": "python",
    "파이썬": "python",
    "java": "java",
    "자바": "java",
    "javascript": "javascript",
    "자바스크립트": "javascript",
    "typescript": "typescript",
    "타입스크립트": "typescript",
    "kotlin": "kotlin",
    "코틀린": "kotlin",
    "go": "go",
    "golang": "go",
}
_FRAMEWORK_HINTS = {
    "spring boot": "spring-boot",
    "springboot": "spring-boot",
    "스프링부트": "spring-boot",
    "spring": "spring",
    "fastapi": "fastapi",
    "django": "django",
    "react": "react",
    "리액트": "react",
    "vue": "vue",
    "next.js": "next.js",
    "nextjs": "next.js",
}
_DEFAULT_FEATURE_NAME = "사용자 요청 기반 기능"


class AgentOrchestrator:
    """Hybrid intent 분류 후 intent별 handler로 위임."""

    _classifier = HybridIntentClassifier()

    async def run_agentic_rag(
        self,
        request: AgenticRagRequest,
    ) -> AgenticRagResponseData:
        """최상위 Agentic RAG 흐름: intent 분류 → route 선택 → 선택적 RAG → 실행."""

        t0 = time.perf_counter()
        steps = ["natural_language_intent_classification"]
        intent = self._classify_agentic_intent(request)
        route = AgentRouter().route(intent, request.model_dump())
        service_name = route["service_name"]
        steps.append("tool_handler_selection")

        references: list[Any] = []
        rag_used = False
        should_use_rag = self._should_use_rag(request)
        if intent == IntentType.FEATURE_TEMPLATE_GENERATE and should_use_rag:
            steps.append("rag_retrieval")
            references = self._retrieve_references(request.message)
            rag_used = bool(references)
        elif should_use_rag:
            steps.append("rag_retrieval_delegated_to_chat_handler")
        else:
            steps.append("rag_retrieval_skipped")

        if intent == IntentType.FEATURE_TEMPLATE_GENERATE:
            response = self._run_feature_template_generate(
                request,
                references=references,
                service_name=service_name,
                steps=steps,
                t0=t0,
                rag_used=rag_used,
            )
            return response

        chat_request = ChatRequest(
            message=request.message,
            context=request.context,
            useRag=True if should_use_rag else request.useRag,
        )
        steps.append("chat_handler_execution")
        chat_result = await self.run_chat(chat_request)
        rag_used = chat_result.ragUsed
        references = chat_result.references
        latency_ms = max(0, int((time.perf_counter() - t0) * 1000))
        trace = AgenticRagTrace(
            classifier="AgenticRuleClassifier",
            intent=IntentType.CHAT,
            serviceName=service_name,
            handler="AgentOrchestrator.run_chat",
            steps=steps + ["result_serialization"],
            ragUsed=rag_used,
            references=references,
            latencyMs=latency_ms,
        )
        return AgenticRagResponseData(
            intent=IntentType.CHAT,
            resultType="chat",
            result=chat_result.model_dump(),
            trace=trace,
        )

    async def run_chat(self, request: ChatRequest) -> ChatResponseData:
        t0 = time.perf_counter()
        result = self._classifier.classify(request.message)
        intent = result.intent
        agent_mode = result.mode
        handler = _HANDLER_MAP[intent]
        handler_name = type(handler).__name__
        tool_candidates = _TOOL_REGISTRY.get_tool_names_for_intent(intent)
        steps = list(result.steps) + [
            "tool_candidate_selection",
            "handler_dispatch",
        ]
        trace = AgentTrace(
            classifier=result.classifier_name,
            handler=handler_name,
            llmIntentUsed=result.llm_intent_used,
            steps=steps,
            latencyMs=0,
            toolCandidates=tool_candidates,
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
                toolCandidates=tool_candidates,
            )
        return out.model_copy(
            update={"agent": out.agent.model_copy(update={"trace": new_trace})}
        )

    def _run_feature_template_generate(
        self,
        request: AgenticRagRequest,
        *,
        references: list[Any],
        service_name: str,
        steps: list[str],
        t0: float,
        rag_used: bool,
    ) -> AgenticRagResponseData:
        feature_request, inferred = self._build_feature_template_request(
            request,
            references=references,
        )
        steps.append("feature_template_request_resolution")
        result = FeatureTemplateGenerator().generate(feature_request)
        steps.append("feature_template_generate_execution")
        latency_ms = max(0, int((time.perf_counter() - t0) * 1000))
        trace = AgenticRagTrace(
            classifier="AgenticRuleClassifier",
            intent=IntentType.FEATURE_TEMPLATE_GENERATE,
            serviceName=service_name,
            handler="FeatureTemplateGenerator.generate",
            steps=steps + ["result_serialization"],
            ragUsed=rag_used,
            references=references,
            inferredFields=inferred,
            latencyMs=latency_ms,
        )
        return AgenticRagResponseData(
            intent=IntentType.FEATURE_TEMPLATE_GENERATE,
            resultType="feature_template",
            result={
                "template": result.template.model_dump(),
                "source": result.source,
                "request": feature_request.model_dump(),
            },
            trace=trace,
        )

    @staticmethod
    def _classify_agentic_intent(request: AgenticRagRequest) -> IntentType:
        if request.featureTemplate is not None:
            return IntentType.FEATURE_TEMPLATE_GENERATE

        text = request.message
        lower_fold = text.lower().replace(" ", "")
        has_feature_hint = any(
            hint.lower().replace(" ", "") in lower_fold
            for hint in _FEATURE_GENERATE_HINTS
        )
        has_action_hint = any(hint in text for hint in _FEATURE_ACTION_HINTS)
        if has_feature_hint and has_action_hint:
            return IntentType.FEATURE_TEMPLATE_GENERATE
        return IntentType.CHAT

    @staticmethod
    def _should_use_rag(request: AgenticRagRequest) -> bool:
        if not settings.RAG_ENABLED:
            return False
        if request.useRag is True:
            return True
        lower = request.message.lower()
        return any(hint in lower for hint in _RAG_HINTS)

    @staticmethod
    def _retrieve_references(message: str) -> list[Any]:
        try:
            refs = RetrieverService().retrieve(message, settings.RAG_TOP_K)
            return [ref.model_dump() for ref in refs]
        except Exception as exc:
            logger.warning(
                "agentic_rag retrieve skipped errorType=%s",
                type(exc).__name__,
            )
            return []

    @staticmethod
    def _build_feature_template_request(
        request: AgenticRagRequest,
        *,
        references: list[Any],
    ) -> tuple[FeatureTemplateGenerateRequest, dict[str, Any]]:
        if request.featureTemplate is not None:
            ref = dict(request.featureTemplate.referenceContext or {})
            AgentOrchestrator._merge_agentic_reference_context(
                ref,
                request=request,
                references=references,
            )
            return (
                request.featureTemplate.model_copy(
                    update={"referenceContext": ref or None},
                ),
                {},
            )

        inferred = AgentOrchestrator._infer_feature_template_fields(request.message)
        ref: dict[str, Any] = {}
        AgentOrchestrator._merge_agentic_reference_context(
            ref,
            request=request,
            references=references,
        )
        feature_request = FeatureTemplateGenerateRequest(
            language=inferred["language"],
            framework=inferred["framework"],
            featureName=inferred["featureName"],
            level=inferred["level"],
            includeCode=True,
            includeMissions=True,
            includeInterview=True,
            referenceContext=ref or None,
        )
        return feature_request, inferred

    @staticmethod
    def _merge_agentic_reference_context(
        ref: dict[str, Any],
        *,
        request: AgenticRagRequest,
        references: list[Any],
    ) -> None:
        ref["agenticUserMessage"] = request.message
        if request.context:
            ref["userContext"] = request.context
        if references:
            ref["ragReferences"] = references

    @staticmethod
    def _infer_feature_template_fields(message: str) -> dict[str, Any]:
        lower = message.lower()
        language = next(
            (value for key, value in _LANGUAGE_HINTS.items() if key in lower),
            "java",
        )
        framework = next(
            (value for key, value in _FRAMEWORK_HINTS.items() if key in lower),
            None,
        )
        feature_name = AgentOrchestrator._infer_feature_name(message)
        level = DifficultyLevel.BEGINNER
        if "advanced" in lower or "고급" in lower:
            level = DifficultyLevel.ADVANCED
        elif "intermediate" in lower or "중급" in lower:
            level = DifficultyLevel.INTERMEDIATE
        return {
            "language": language,
            "framework": framework,
            "featureName": feature_name,
            "level": level,
        }

    @staticmethod
    def _infer_feature_name(message: str) -> str:
        patterns = (
            r"(?P<name>[가-힣A-Za-z0-9_\- ]{1,40})\s*기능\s*템플릿",
            r"(?P<name>[가-힣A-Za-z0-9_\- ]{1,40})\s*기능템플릿",
            r"(?P<name>[가-힣A-Za-z0-9_\- ]{1,40})\s*기능\s*(?:명세|요구사항)",
        )
        for pattern in patterns:
            match = re.search(pattern, message)
            if not match:
                continue
            name = AgentOrchestrator._clean_feature_name(match.group("name"))
            if name:
                return name
        return _DEFAULT_FEATURE_NAME

    @staticmethod
    def _clean_feature_name(value: str) -> str:
        cleaned = value.strip(" .,;:，。")
        for token in (
            "java",
            "자바",
            "python",
            "파이썬",
            "spring",
            "스프링",
            "fastapi",
            "react",
            "로",
            "으로",
        ):
            cleaned = re.sub(
                rf"\b{re.escape(token)}\b",
                "",
                cleaned,
                flags=re.IGNORECASE,
            )
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned or _DEFAULT_FEATURE_NAME
